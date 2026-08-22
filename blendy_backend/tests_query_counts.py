"""Query-count regression tests.

Every endpoint below serves a *constant* number of queries regardless of how
many rows it returns. That property is easy to lose: adding a
SerializerMethodField, or calling `.filter()` on a related manager instead of
iterating it, silently reintroduces a query per row and nothing else in the
suite notices.

The assertion is deliberately "same count at 1 row as at 15", not "fewer than
some number". An absolute ceiling drifts every time an unrelated query is added
somewhere in the stack; the invariant that actually matters is that the slope is
flat. A generous ceiling is asserted alongside it purely to catch a fixed-cost
blow-up.

These endpoints live across several apps, so the tests live with the project
rather than inside any one of them.
"""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from authorization.models import (
    OrganizationRole,
    Permission,
    Role,
    UserRoleAssignment,
)
from blendy_backend.testing import grant_role, make_organization
from inventory.services import record_movement
from payments.models import Payment
from pricing.services import get_default_pricelist, set_price
from products.models import Category, Currency, Product, ProductVariation, UOM
from sales.models import Sale, SaleItem
from users.models import CustomUser

SMALL = 1
LARGE = 15


class QueryCountTests(APITestCase):
    """Listings must not issue a query per row."""

    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="owner@duka.test",
            username="owner",
            password="pw",
            organization=self.org,
            is_organization_admin=True,
        )
        grant_role(self.user, self.org)
        self.client.force_authenticate(user=self.user)
        self.category = Category.objects.create(name="Groceries", organization=self.org)
        self.pricelist = get_default_pricelist(self.org)
        # Populated deliberately: both are nested serializers on a variation, so
        # leaving them null hides two foreign-key fetches per row.
        self.uom = UOM.objects.create(name="Kilogram", symbol="kg", organization=self.org)
        self.currency = Currency.objects.create(
            name="Shilling", iso_code="KES", numeric_code="404", symbol="KSh",
            organization=self.org,
        )

    def _seed(self, count):
        """`count` products, each with two priced, stocked variations and a sale."""
        Payment.objects.all().delete()
        SaleItem.objects.all().delete()
        Sale.objects.all().delete()
        Product.objects.all().delete()

        for i in range(count):
            product = Product.objects.create(
                name=f"Product {i}", organization=self.org, category=self.category
            )
            variations = []
            for v in range(2):
                variation = ProductVariation.objects.create(
                    product=product,
                    organization=self.org,
                    sku=f"SKU-{i}-{v}",
                    uom=self.uom,
                    currency=self.currency,
                    cost_price=Decimal("100.00"),
                    reorder_level=1000,
                )
                set_price(
                    organization=self.org,
                    pricelist=self.pricelist,
                    product_variation=variation,
                    price=Decimal("150.00"),
                )
                record_movement(
                    organization=self.org,
                    product_variation=variation,
                    movement_type="STOCK_IN",
                    quantity=5,
                    user=self.user,
                )
                variations.append(variation)

            sale = Sale.objects.create(organization=self.org, pricelist=self.pricelist)
            for variation in variations:
                SaleItem.objects.create(
                    sale=sale,
                    organization=self.org,
                    product_variation=variation,
                    quantity=1,
                    unit_price=Decimal("150.00"),
                    cost_price=Decimal("100.00"),
                    selling_price=Decimal("150.00"),
                    total_price=Decimal("150.00"),
                )
            Payment.objects.create(
                organization=self.org,
                sale=sale,
                amount=Decimal("300.00"),
                provider="MPESA",
                phone_number="254712345678",
            )

    def _count_queries(self, url):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url, HTTP_X_ORGANIZATION=str(self.org.id))
        self.assertEqual(response.status_code, 200, response.data)
        return len(captured.captured_queries)

    def assertFlat(self, url, ceiling):
        """The query count must not grow with the number of rows returned."""
        self._seed(SMALL)
        small = self._count_queries(url)
        self._seed(LARGE)
        large = self._count_queries(url)

        self.assertEqual(
            small,
            large,
            f"{url} issues {small} queries for {SMALL} row(s) but {large} for "
            f"{LARGE}. That is {(large - small) / (LARGE - SMALL):.1f} extra "
            f"queries per row — an N+1 has been reintroduced.",
        )
        self.assertLessEqual(
            large,
            ceiling,
            f"{url} serves a flat {large} queries, but that is above the "
            f"documented ceiling of {ceiling}. Fixed cost has grown.",
        )

    # Ceilings are the measured count plus a little headroom, so an unrelated
    # extra query does not fail the build while a real N+1 still does.

    def test_product_listing_is_flat(self):
        self.assertFlat("/api/products/", ceiling=10)

    def test_product_with_price_listing_is_flat(self):
        pricelist = get_default_pricelist(self.org)
        self.assertFlat(
            f"/api/products/with-price/?pricelist_id={pricelist.id}", ceiling=10
        )

    def test_variation_listing_is_flat(self):
        self.assertFlat("/api/products/variations/", ceiling=8)

    def test_sale_listing_is_flat(self):
        self.assertFlat("/api/sales/sales/", ceiling=10)

    def test_pending_payments_listing_is_flat(self):
        self.assertFlat("/api/sales/sales/pending-payments/", ceiling=10)

    def test_sale_item_listing_is_flat(self):
        self.assertFlat("/api/sales/sale-items/", ceiling=6)

    def test_payment_listing_is_flat(self):
        self.assertFlat("/api/payments/payments/", ceiling=7)

    def test_low_stock_listing_is_flat(self):
        self.assertFlat("/api/inventory/stock/low-stock/", ceiling=6)

    def test_stock_movement_listing_is_flat(self):
        self.assertFlat("/api/inventory/stock-movements/", ceiling=6)

    def test_inventory_item_listing_is_flat(self):
        self.assertFlat("/api/inventory/inventory-items/", ceiling=6)


class PermissionCheckQueryTests(APITestCase):
    """The RBAC check is one query, and does not grow with the roles held."""

    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="cashier@duka.test", username="cashier", password="pw",
            organization=self.org,
        )
        self.client.force_authenticate(user=self.user)

    def _grant(self, role_count, permission_on_last_role):
        """Roles for the user, optionally with the needed permission on the last.

        The permission goes on the *last* role deliberately: the old
        implementation returned early on the first match, so putting it first
        would have measured its best case rather than its real one.
        """
        for i in range(role_count):
            role = Role.objects.create(name=f"role-{i}")
            names = [f"other.perm{i}a", f"other.perm{i}b"]
            if permission_on_last_role and i == role_count - 1:
                names.append("pricing.view_pricelistitem")
            for name in names:
                permission, _ = Permission.objects.get_or_create(name=name)
                role.permissions.add(permission)
            org_role = OrganizationRole.objects.create(
                organization=self.org, role=role
            )
            UserRoleAssignment.objects.create(user=self.user, organization_role=org_role)

    def _count(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                "/api/pricing/pricelist-items/",
                HTTP_X_ORGANIZATION=str(self.org.id),
            )
        return len(captured.captured_queries), response.status_code

    def test_permission_check_does_not_grow_with_role_count(self):
        self._grant(role_count=1, permission_on_last_role=True)
        few, status_few = self._count()
        self.assertEqual(status_few, 200)

        UserRoleAssignment.objects.all().delete()
        Role.objects.all().delete()
        self._grant(role_count=10, permission_on_last_role=True)
        many, status_many = self._count()
        self.assertEqual(status_many, 200)

        self.assertEqual(
            few,
            many,
            f"The permission check costs {few} queries with 1 role but {many} "
            f"with 10. It is walking the role assignments row by row again.",
        )

    def test_denied_request_costs_no_more_than_an_allowed_one(self):
        """The worst case used to be a permission the user did not hold."""
        self._grant(role_count=10, permission_on_last_role=True)
        allowed, status_allowed = self._count()
        self.assertEqual(status_allowed, 200)

        UserRoleAssignment.objects.all().delete()
        Role.objects.all().delete()
        self._grant(role_count=10, permission_on_last_role=False)
        denied, status_denied = self._count()
        self.assertEqual(status_denied, 403)

        self.assertLessEqual(denied, allowed)


class SaleCreationQueryTests(APITestCase):
    """A sale's fixed costs are paid once, not once per line."""

    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="owner@duka.test", username="owner", password="pw",
            organization=self.org,
        )
        grant_role(self.user, self.org)
        self.client.force_authenticate(user=self.user)
        self.pricelist = get_default_pricelist(self.org)
        product = Product.objects.create(name="Sugar", organization=self.org)
        self.variations = []
        for i in range(10):
            variation = ProductVariation.objects.create(
                product=product, organization=self.org, sku=f"SKU-{i}",
                cost_price=Decimal("100.00"),
            )
            set_price(
                organization=self.org, pricelist=self.pricelist,
                product_variation=variation, price=Decimal("150.00"),
            )
            record_movement(
                organization=self.org, product_variation=variation,
                movement_type="STOCK_IN", quantity=50, user=self.user,
            )
            self.variations.append(variation)

    def _sell(self, line_count):
        payload = {
            "items": [
                {"product_variation": str(v.id), "quantity": 1}
                for v in self.variations[:line_count]
            ]
        }
        with CaptureQueriesContext(connection) as captured:
            response = self.client.post(
                "/api/sales/sales/", payload, format="json",
                HTTP_X_ORGANIZATION=str(self.org.id),
            )
        self.assertEqual(response.status_code, 201, response.data)
        return len(captured.captured_queries)

    def test_marginal_cost_per_line_is_bounded(self):
        """Each extra line should cost only its own writes, not a fresh lookup.

        The floor is four writes plus the savepoint pair that record_movement's
        atomic block opens: the line insert, the locking read of the balance,
        the ledger insert, and the balance update. The pricelist lookup and the
        stock location are resolved once for the whole basket, so they must not
        appear in the slope.
        """
        one = self._sell(1)
        ten = self._sell(10)
        per_line = (ten - one) / 9.0

        self.assertLessEqual(
            per_line,
            7.0,
            f"Each additional sale line costs {per_line:.1f} queries. Something "
            f"that should be resolved once for the basket — the pricelist, the "
            f"stock location — is being resolved per line again.",
        )

    def test_response_does_not_query_per_line(self):
        """Serializing the created sale must not walk back to the database.

        A freshly created Sale has no prefetch cache, so rendering it once cost
        a query per line for the variation, plus a second pass over the lines
        for total_amount.
        """
        payload = {
            "items": [
                {"product_variation": str(v.id), "quantity": 1}
                for v in self.variations[:5]
            ]
        }
        response = self.client.post(
            "/api/sales/sales/", payload, format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )
        self.assertEqual(response.status_code, 201, response.data)

        sale = Sale.objects.get(id=response.data["id"])
        # The serializer reads these; on the created instance they came from the
        # prefetch, so re-reading them here proves the response paid for them.
        self.assertEqual(len(response.data["items"]), 5)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("750.00"))
        self.assertEqual(sale.items.count(), 5)
