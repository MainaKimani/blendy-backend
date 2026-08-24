"""The seeded permission catalogue, and the access it produces.

Before this was seeded, `HasUserPermission` matched no Permission row at all, so
every guarded endpoint refused everyone — an owner onboarded seconds earlier as
ORG_ADMIN got 403 on their own pricelists. These tests assert the fix from the
outside: through the API, as the roles a real shop actually has.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from authorization.models import OrganizationRole, Permission, Role, UserRoleAssignment
from authorization.rbac import (
    CASHIER,
    DEFAULT_ORGANIZATION_ROLES,
    ORG_ADMIN,
    PLATFORM_ADMIN,
    ROLES,
    SUPPORT_AGENT,
    VIEWER,
    enable_default_roles,
    permission_names,
    sync_rbac,
    tenant_permission_names,
)
from blendy_backend.testing import make_organization
from organization.models import Organization
from pricing.services import get_default_pricelist
from products.models import Category, Product, ProductVariation
from users.models import CustomUser


class CatalogueTests(APITestCase):
    """The catalogue is seeded by migration and safe to re-apply."""

    def test_every_declared_permission_exists(self):
        missing = set(permission_names()) - set(
            Permission.objects.values_list("name", flat=True)
        )

        self.assertEqual(missing, set(), f"Not seeded: {sorted(missing)}")

    def test_every_permission_a_view_checks_actually_exists(self):
        """The regression: these were checked against rows nothing created.

        Kept as an explicit list rather than derived from the catalogue, so that
        renaming a permission in rbac.py without updating the viewset that
        checks it fails here instead of silently locking people out.
        """
        checked_by_views = [
            "pricing.view_pricelist",
            "pricing.add_pricelist",
            "pricing.change_pricelist",
            "pricing.delete_pricelist",
            "pricing.view_pricelistitem",
            "pricing.add_pricelistitem",
            "pricing.change_pricelistitem",
            "pricing.delete_pricelistitem",
        ]

        for name in checked_by_views:
            with self.subTest(permission=name):
                self.assertTrue(Permission.objects.filter(name=name).exists())

    def test_org_admin_holds_the_whole_tenant_catalogue(self):
        """Derived, not listed — a forgotten entry would lock the owner out."""
        role = Role.objects.get(name=ORG_ADMIN)

        held = set(role.permissions.values_list("name", flat=True))

        self.assertEqual(held, set(tenant_permission_names()))

    def test_org_admin_holds_no_platform_permission(self):
        """The load-bearing separation.

        ORG_ADMIN is derived from a pool. If that pool were the whole catalogue
        rather than the tenant half, every shop owner would silently gain
        platform.access_tenants — and with it, read access to every other shop
        in the deployment.
        """
        held = set(
            Role.objects.get(name=ORG_ADMIN).permissions.values_list("name", flat=True)
        )

        self.assertEqual([n for n in held if n.startswith("platform.")], [])

    def test_cashier_cannot_change_prices_or_manage_staff(self):
        """US-15's restriction, stated as what the role must not hold."""
        held = set(
            Role.objects.get(name=CASHIER).permissions.values_list("name", flat=True)
        )

        for forbidden in [
            "pricing.add_pricelistitem",
            "pricing.change_pricelistitem",
            "pricing.delete_pricelistitem",
            "products.change_product",
            "users.add_customuser",
            "users.change_customuser",
            "authorization.add_userroleassignment",
            "reports.view_sales_report",
            "reports.view_margin_report",
            "sales.void_sale",
        ]:
            with self.subTest(permission=forbidden):
                self.assertNotIn(forbidden, held)

    def test_cashier_can_sell_and_see_stock(self):
        held = set(
            Role.objects.get(name=CASHIER).permissions.values_list("name", flat=True)
        )

        for required in [
            "sales.add_sale",
            "payments.add_payment",
            "products.view_product",
            "pricing.view_pricelistitem",
            "inventory.view_inventoryitem",
            "inventory.view_lowstock",
        ]:
            with self.subTest(permission=required):
                self.assertIn(required, held)

    def test_syncing_twice_changes_nothing(self):
        before = Permission.objects.count()

        summary = sync_rbac()

        self.assertEqual(summary["permissions_created"], 0)
        self.assertEqual(summary["roles_created"], 0)
        self.assertEqual(Permission.objects.count(), before)

    def test_sync_repairs_a_role_whose_permissions_were_stripped(self):
        role = Role.objects.get(name=ORG_ADMIN)
        role.permissions.clear()

        sync_rbac()

        role.refresh_from_db()
        self.assertEqual(role.permissions.count(), len(tenant_permission_names()))


class OnboardedOwnerTests(APITestCase):
    """An owner onboarded through the API can use their own shop."""

    def setUp(self):
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)
        response = self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Mama Duka", "slug": "mama-duka"},
                "user": {
                    "email": "owner@mamaduka.co.ke",
                    "username": "owner",
                    "password": "pw",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.org = Organization.objects.get(slug="mama-duka")
        self.owner = CustomUser.objects.get(email="owner@mamaduka.co.ke")
        self.headers = {"HTTP_X_ORGANIZATION": str(self.org.id)}

    def test_the_owner_can_read_their_own_pricelists(self):
        """The regression, exactly as reported: this used to be a 403."""
        self.client.force_authenticate(user=self.owner)

        response = self.client.get("/api/pricing/pricelists/", **self.headers)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Default Pricelist")

    def test_the_owner_can_price_a_variation(self):
        self.client.force_authenticate(user=self.owner)
        product = Product.objects.create(name="Sugar", organization=self.org)
        variation = ProductVariation.objects.create(
            product=product, organization=self.org
        )

        response = self.client.post(
            "/api/pricing/pricelist-items/",
            {
                "pricelist": str(get_default_pricelist(self.org).id),
                "product_variation": str(variation.id),
                "price": "165.00",
            },
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_onboarding_enables_every_built_in_role(self):
        """So the owner can hire a cashier, and registration has a role to give."""
        enabled = set(
            OrganizationRole.objects.filter(organization=self.org).values_list(
                "role__name", flat=True
            )
        )

        self.assertEqual(enabled, set(DEFAULT_ORGANIZATION_ROLES))

    def test_the_owner_holds_every_permission(self):
        self.assertEqual(
            self.owner.get_permission_names(), frozenset(tenant_permission_names())
        )


class CashierAccessTests(APITestCase):
    """US-15 end to end: a cashier sells, and is refused everything else."""

    def setUp(self):
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)
        self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Mama Duka", "slug": "mama-duka"},
                "user": {
                    "email": "owner@mamaduka.co.ke",
                    "username": "owner",
                    "password": "pw",
                },
            },
            format="json",
        )
        self.org = Organization.objects.get(slug="mama-duka")
        self.headers = {"HTTP_X_ORGANIZATION": str(self.org.id)}

        self.cashier = CustomUser.objects.create_user(
            email="cashier@mamaduka.co.ke", username="cashier", password="pw",
            organization=self.org,
        )
        UserRoleAssignment.objects.create(
            user=self.cashier,
            organization_role=OrganizationRole.objects.get(
                organization=self.org, role__name=CASHIER
            ),
        )
        self.client.force_authenticate(user=self.cashier)

    def test_a_cashier_can_see_what_things_cost(self):
        response = self.client.get("/api/pricing/pricelist-items/", **self.headers)

        self.assertEqual(response.status_code, 200, response.data)

    def test_a_cashier_cannot_change_what_things_cost(self):
        product = Product.objects.create(name="Sugar", organization=self.org)
        variation = ProductVariation.objects.create(
            product=product, organization=self.org
        )

        response = self.client.post(
            "/api/pricing/pricelist-items/",
            {
                "pricelist": str(get_default_pricelist(self.org).id),
                "product_variation": str(variation.id),
                "price": "1.00",
            },
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_a_cashier_cannot_create_a_pricelist(self):
        response = self.client.post(
            "/api/pricing/pricelists/",
            {"name": "Cheap"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_a_cashiers_permissions_are_scoped_to_their_own_shop(self):
        """Holding CASHIER at one shop grants nothing at another."""
        other = Organization.objects.create(name="Other", slug="other")
        self.cashier.organization = other
        self.cashier.save(update_fields=["organization"])

        # The assignment still exists, but it belongs to the first shop.
        self.assertEqual(self.cashier.get_permission_names(), frozenset())


class ViewerRoleTests(APITestCase):
    """The role self-registration hands out.

    /api/users/register/ is open to anonymous callers and needs only an
    organization id, so this role's scope is set by who can obtain it — not by
    what "viewer" suggests elsewhere.
    """

    def setUp(self):
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)
        self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Mama Duka", "slug": "mama-duka"},
                "user": {
                    "email": "owner@mamaduka.co.ke",
                    "username": "owner",
                    "password": "pw",
                },
            },
            format="json",
        )
        self.org = Organization.objects.get(slug="mama-duka")
        self.headers = {"HTTP_X_ORGANIZATION": str(self.org.id)}
        self.client.force_authenticate(user=None)

    def _register(self, email="shopper@example.com", username="shopper"):
        return self.client.post(
            "/api/users/register/",
            {"email": email, "username": username, "password": "pw"},
            format="json",
            **self.headers,
        )

    def test_registration_actually_assigns_the_role(self):
        """The regression: this looked up a role that never existed.

        Role.DoesNotExist was swallowed, so every self-registered user came out
        with no role at all and the assignment code had never once run.
        """
        response = self._register()

        self.assertEqual(response.status_code, 201, response.data)
        user = CustomUser.objects.get(email="shopper@example.com")
        self.assertEqual(
            list(
                UserRoleAssignment.objects.filter(user=user).values_list(
                    "organization_role__role__name", flat=True
                )
            ),
            [VIEWER],
        )

    def test_a_registered_user_can_read_the_catalogue(self):
        self._register()
        user = CustomUser.objects.get(email="shopper@example.com")

        self.assertIn("products.view_product", user.get_permission_names())

    def test_a_registered_user_cannot_see_the_shops_money_or_stock(self):
        """The reason this role is scoped the way it is.

        Anyone who learns an organization's id can register into it, so VIEWER
        must not carry sales, payments or stock.
        """
        self._register()
        user = CustomUser.objects.get(email="shopper@example.com")
        held = user.get_permission_names()

        for forbidden in [
            "sales.view_sale",
            "payments.view_payment",
            "inventory.view_inventoryitem",
            "inventory.view_stockmovement",
            "users.view_customuser",
            "reports.view_sales_report",
        ]:
            with self.subTest(permission=forbidden):
                self.assertNotIn(forbidden, held)

    def test_a_registered_user_cannot_read_pricelists(self):
        """Excluded on purpose, and enforced — /api/products/ exposes only the
        *default* price, so a second list (wholesale, staff) would otherwise
        leak through the pricing endpoints."""
        self._register()
        user = CustomUser.objects.get(email="shopper@example.com")
        self.assertNotIn("pricing.view_pricelistitem", user.get_permission_names())

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/pricing/pricelist-items/", **self.headers)

        self.assertEqual(response.status_code, 403)

    def test_viewer_holds_nothing_a_cashier_does_not(self):
        viewer = set(Role.objects.get(name=VIEWER).permissions.values_list("name", flat=True))
        cashier = set(Role.objects.get(name=CASHIER).permissions.values_list("name", flat=True))

        self.assertTrue(viewer.issubset(cashier), f"Extra: {sorted(viewer - cashier)}")

    def test_enabling_default_roles_is_idempotent(self):
        before = OrganizationRole.objects.count()

        self.assertEqual(enable_default_roles(), 0)
        self.assertEqual(OrganizationRole.objects.count(), before)

    def test_an_organization_predating_the_role_gets_it_enabled(self):
        """What the backfill migration does, exercised through the helper."""
        old_shop = Organization.objects.create(name="Old Shop", slug="old-shop")
        self.assertEqual(
            OrganizationRole.objects.filter(organization=old_shop).count(), 0
        )

        enable_default_roles()

        enabled = set(
            OrganizationRole.objects.filter(organization=old_shop).values_list(
                "role__name", flat=True
            )
        )
        self.assertEqual(enabled, set(DEFAULT_ORGANIZATION_ROLES))


class EnforcedAccessTests(APITestCase):
    """Sales and inventory now consult the catalogue.

    Before this, both gated on IsAuthenticated + IsOrganizationUser alone, so
    any member of an organization — including a self-registered VIEWER — could
    read its sales and its stock position. The roles were scoped correctly; the
    endpoints simply never asked.
    """

    def setUp(self):
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)
        self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Mama Duka", "slug": "mama-duka"},
                "user": {
                    "email": "owner@mamaduka.co.ke",
                    "username": "owner",
                    "password": "pw",
                },
            },
            format="json",
        )
        self.org = Organization.objects.get(slug="mama-duka")
        self.headers = {"HTTP_X_ORGANIZATION": str(self.org.id)}
        self.owner = CustomUser.objects.get(email="owner@mamaduka.co.ke")

        self.cashier = self._staff("cashier@mamaduka.co.ke", "till", CASHIER)
        self.viewer = self._staff("shopper@example.com", "shopper", VIEWER)

        category = Category.objects.create(name="Groceries", organization=self.org)
        self.product = Product.objects.create(
            name="Sugar", organization=self.org, category=category
        )
        self.variation = ProductVariation.objects.create(
            product=self.product, organization=self.org, sku="SUG-1KG"
        )
        from pricing.services import set_price

        set_price(
            organization=self.org,
            pricelist=get_default_pricelist(self.org),
            product_variation=self.variation,
            price=Decimal("165.00"),
        )
        from inventory.services import record_movement

        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=100,
            user=self.owner,
        )

    def _staff(self, email, username, role_name):
        user = CustomUser.objects.create_user(
            email=email, username=username, password="pw", organization=self.org
        )
        UserRoleAssignment.objects.create(
            user=user,
            organization_role=OrganizationRole.objects.get(
                organization=self.org, role__name=role_name
            ),
        )
        return user

    def _as(self, user):
        self.client.force_authenticate(user=user)

    # --- the gap this closes ------------------------------------------------

    def test_a_viewer_can_no_longer_read_the_shops_sales(self):
        self._as(self.viewer)

        response = self.client.get("/api/sales/sales/", **self.headers)

        self.assertEqual(response.status_code, 403)

    def test_a_viewer_can_no_longer_read_the_shops_stock(self):
        self._as(self.viewer)

        for url in [
            "/api/inventory/inventory-items/",
            "/api/inventory/stock-movements/",
            "/api/inventory/stock/low-stock/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url, **self.headers).status_code, 403
                )

    # --- guest checkout must survive ---------------------------------------

    def test_an_anonymous_customer_can_still_check_out(self):
        """The one path that must stay open. A customer holds no role at all."""
        self._as(None)

        response = self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {"product_variation": str(self.variation.id), "quantity": 1}
                ]
            },
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_an_anonymous_customer_still_cannot_read_sales(self):
        self._as(None)

        response = self.client.get("/api/sales/sales/", **self.headers)

        self.assertIn(response.status_code, (401, 403))

    # --- the cashier does their job ----------------------------------------

    def test_a_cashier_can_sell_and_see_stock(self):
        self._as(self.cashier)

        sale = self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {"product_variation": str(self.variation.id), "quantity": 2}
                ]
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(sale.status_code, 201, sale.data)

        for url in [
            "/api/sales/sales/",
            "/api/sales/sales/pending-payments/",
            "/api/inventory/inventory-items/",
            "/api/inventory/stock/low-stock/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url, **self.headers).status_code, 200
                )

    def test_a_cashier_cannot_move_stock(self):
        """Restocking and adjusting are the owner's, not the till's."""
        self._as(self.cashier)

        for url, body in [
            (
                "/api/inventory/stock/restock/",
                {"product_variation": str(self.variation.id), "quantity": 10},
            ),
            (
                "/api/inventory/stock/adjust/",
                {
                    "product_variation": str(self.variation.id),
                    "quantity": -1,
                    "reason": "shrinkage",
                },
            ),
        ]:
            with self.subTest(url=url):
                response = self.client.post(
                    url, body, format="json", **self.headers
                )
                self.assertEqual(response.status_code, 403, response.data)

    def test_a_cashier_cannot_delete_a_sale(self):
        self._as(self.owner)
        sale_id = self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {"product_variation": str(self.variation.id), "quantity": 1}
                ]
            },
            format="json",
            **self.headers,
        ).data["id"]

        self._as(self.cashier)
        response = self.client.delete(f"/api/sales/sales/{sale_id}/", **self.headers)

        self.assertEqual(response.status_code, 403)

    # --- the owner is unaffected -------------------------------------------

    def test_the_owner_can_still_do_everything(self):
        self._as(self.owner)

        restock = self.client.post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 10},
            format="json",
            **self.headers,
        )
        self.assertEqual(restock.status_code, 201, restock.data)

        for url in [
            "/api/sales/sales/",
            "/api/inventory/inventory-items/",
            "/api/inventory/stock-movements/",
            "/api/inventory/locations/",
            "/api/inventory/stock-takes/",
            "/api/inventory/stock-take-items/",
            "/api/inventory/stock/low-stock/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url, **self.headers).status_code, 200
                )

    def test_every_permission_these_viewsets_check_exists_in_the_catalogue(self):
        """A viewset checking an unseeded name locks everyone out silently."""
        from authorization.rbac import permission_names

        catalogue = set(permission_names())
        for name in [
            "sales.view_sale", "sales.change_sale", "sales.delete_sale",
            "sales.view_saleitem", "sales.add_saleitem",
            "sales.change_saleitem", "sales.delete_saleitem",
            "inventory.view_location", "inventory.add_location",
            "inventory.view_inventoryitem", "inventory.view_stockmovement",
            "inventory.view_stocktake", "inventory.view_stocktakeitem",
            "inventory.restock_stock", "inventory.adjust_stock",
            "inventory.view_lowstock",
        ]:
            with self.subTest(permission=name):
                self.assertIn(name, catalogue)


class PlatformRoleTests(APITestCase):
    """Blendy's own roles: seeded globally, enabled on HQ, absent from shops."""

    def setUp(self):
        from organization.services import get_platform_organization

        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")

    def _held(self, role_name):
        return set(
            Role.objects.get(name=role_name).permissions.values_list("name", flat=True)
        )

    # --- the separation that matters most ---------------------------------

    def test_platform_permissions_exist(self):
        from authorization.rbac import platform_permission_names

        missing = set(platform_permission_names()) - set(
            Permission.objects.values_list("name", flat=True)
        )

        self.assertEqual(missing, set())

    def test_no_tenant_role_holds_a_platform_permission(self):
        """A shop's staff must never hold a key to another shop."""
        from authorization.rbac import DEFAULT_ORGANIZATION_ROLES

        for role_name in DEFAULT_ORGANIZATION_ROLES:
            with self.subTest(role=role_name):
                held = self._held(role_name)
                self.assertEqual(
                    sorted(n for n in held if n.startswith("platform.")), []
                )

    def test_platform_roles_are_not_enabled_on_any_shop(self):
        from authorization.rbac import PLATFORM_ROLES

        enabled = set(
            OrganizationRole.objects.filter(organization=self.shop).values_list(
                "role__name", flat=True
            )
        )

        self.assertEqual(enabled & set(PLATFORM_ROLES), set())

    def test_onboarding_a_new_shop_does_not_enable_platform_roles(self):
        from authorization.rbac import PLATFORM_ROLES

        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)
        self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Second Shop", "slug": "second-shop"},
                "user": {"email": "o2@shop.test", "username": "o2", "password": "pw"},
            },
            format="json",
        )

        enabled = set(
            OrganizationRole.objects.filter(
                organization__slug="second-shop"
            ).values_list("role__name", flat=True)
        )
        self.assertEqual(enabled & set(PLATFORM_ROLES), set())

    # --- what each platform role is for -----------------------------------

    def test_platform_roles_are_enabled_on_hq(self):
        from authorization.rbac import PLATFORM_ROLES

        enabled = set(
            OrganizationRole.objects.filter(organization=self.hq).values_list(
                "role__name", flat=True
            )
        )

        self.assertEqual(set(PLATFORM_ROLES) - enabled, set())

    def test_support_agent_can_cross_the_boundary_but_not_write(self):
        held = self._held(SUPPORT_AGENT)

        self.assertIn("platform.access_tenants", held)
        # Read-only is not enforced separately — it falls out of holding no
        # write permission at all.
        self.assertNotIn("platform.act_as_tenant", held)
        writes = [
            n for n in held
            if any(f".{verb}_" in n for verb in ("add", "change", "delete"))
        ]
        self.assertEqual(writes, [])

    def test_support_agent_can_see_what_a_shop_would_call_about(self):
        held = self._held(SUPPORT_AGENT)

        for name in [
            "sales.view_sale",
            "payments.view_payment",
            "inventory.view_inventoryitem",
            "pricing.view_pricelistitem",
            "products.view_product",
        ]:
            with self.subTest(permission=name):
                self.assertIn(name, held)

    def test_platform_admin_can_act_and_administer(self):
        held = self._held(PLATFORM_ADMIN)

        for name in [
            "platform.access_tenants",
            "platform.act_as_tenant",
            "platform.onboard_organization",
            "platform.manage_platform_staff",
            "platform.view_access_log",
        ]:
            with self.subTest(permission=name):
                self.assertIn(name, held)

    def test_platform_admin_holds_everything_support_does(self):
        self.assertTrue(self._held(SUPPORT_AGENT).issubset(self._held(PLATFORM_ADMIN)))

    # --- resolution through the real chain --------------------------------

    def test_an_hq_user_resolves_platform_permissions(self):
        agent = CustomUser.objects.create_user(
            email="agent@blendy.test", username="agent", password="pw",
            organization=self.hq,
        )
        UserRoleAssignment.objects.create(
            user=agent,
            organization_role=OrganizationRole.objects.get(
                organization=self.hq, role__name=SUPPORT_AGENT
            ),
        )

        held = agent.get_permission_names()

        self.assertIn("platform.access_tenants", held)
        self.assertIn("sales.view_sale", held)
        self.assertNotIn("sales.add_sale", held)

    def test_a_shop_owner_resolves_no_platform_permission(self):
        owner = CustomUser.objects.create_user(
            email="owner@mama-duka.test", username="owner", password="pw",
            organization=self.shop,
        )
        UserRoleAssignment.objects.create(
            user=owner,
            organization_role=OrganizationRole.objects.get(
                organization=self.shop, role__name=ORG_ADMIN
            ),
        )

        held = owner.get_permission_names()

        self.assertIn("sales.add_sale", held)
        self.assertEqual([n for n in held if n.startswith("platform.")], [])

    def test_enabling_platform_roles_is_idempotent(self):
        from authorization.rbac import enable_platform_roles

        before = OrganizationRole.objects.count()

        self.assertEqual(enable_platform_roles(), 0)
        self.assertEqual(OrganizationRole.objects.count(), before)

    def test_enabling_platform_roles_without_hq_is_a_no_op(self):
        from authorization.rbac import enable_platform_roles
        from organization.models import Organization

        Organization.objects.filter(is_platform=True).delete()

        self.assertEqual(enable_platform_roles(), 0)
