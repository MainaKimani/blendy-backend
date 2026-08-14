from decimal import Decimal

from rest_framework.test import APITestCase

from authorization.models import (
    OrganizationRole,
    Permission,
    Role,
    UserRoleAssignment,
)
from blendy_backend.testing import make_organization
from organization.models import Organization
from pricing.models import Pricelist, PricelistItem
from products.models import Product, ProductVariation
from users.models import CustomUser


class PricelistItemTenantIsolationTests(APITestCase):
    """Pricelist items are exposed directly, so they need their own scoping."""

    def setUp(self):
        self.org_a = make_organization("Shop A", "shop-a")
        self.org_b = make_organization("Shop B", "shop-b")

        self.user_a = CustomUser.objects.create_user(
            email="a@shop.test",
            username="a",
            password="pw",
            organization=self.org_a,
            is_organization_admin=True,
        )
        self._grant(
            self.user_a,
            self.org_a,
            ["pricing.view_pricelistitem", "pricing.add_pricelistitem"],
        )

        self.list_a, self.item_a = self._make_pricelist(self.org_a, "Sugar")
        self.list_b, self.item_b = self._make_pricelist(self.org_b, "Flour")

    def _grant(self, user, organization, permission_names):
        """Assign permissions the way the RBAC models intend, via a role."""
        role = Role.objects.create(name=f"role-for-{user.username}")
        for name in permission_names:
            permission, _ = Permission.objects.get_or_create(name=name)
            role.permissions.add(permission)
        org_role = OrganizationRole.objects.create(
            organization=organization, role=role
        )
        UserRoleAssignment.objects.create(user=user, organization_role=org_role)

    def _make_pricelist(self, organization, product_name):
        pricelist = Pricelist.objects.create(
            organization=organization, name=f"{product_name} list"
        )
        product = Product.objects.create(
            name=product_name, organization=organization
        )
        variation = ProductVariation.objects.create(
            product=product, organization=organization
        )
        item = PricelistItem.objects.create(
            organization=organization,
            pricelist=pricelist,
            product_variation=variation,
            price=Decimal("100.00"),
        )
        return pricelist, item

    def test_list_returns_only_the_callers_tenant(self):
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            "/api/pricing/pricelist-items/",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.item_a.id))

    def test_other_tenants_item_is_not_retrievable(self):
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            f"/api/pricing/pricelist-items/{self.item_b.id}/",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 404)

    def _new_variation(self, organization, name):
        product = Product.objects.create(
            name=name, organization=organization
        )
        return ProductVariation.objects.create(
            product=product, organization=organization
        )

    def test_cannot_attach_an_item_to_another_tenants_pricelist(self):
        self.client.force_authenticate(user=self.user_a)
        variation = self._new_variation(self.org_a, "Rice")

        response = self.client.post(
            "/api/pricing/pricelist-items/",
            {
                "pricelist": str(self.list_b.id),
                "product_variation": str(variation.id),
                "price": "200.00",
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(PricelistItem.objects.filter(pricelist=self.list_b).count(), 1)

    def test_created_item_inherits_the_tenant(self):
        self.client.force_authenticate(user=self.user_a)
        variation = self._new_variation(self.org_a, "Rice")

        response = self.client.post(
            "/api/pricing/pricelist-items/",
            {
                "pricelist": str(self.list_a.id),
                "product_variation": str(variation.id),
                "price": "200.00",
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 201)
        item = PricelistItem.objects.get(id=response.data["id"])
        self.assertEqual(item.organization_id, self.org_a.id)


class ProductWithPriceTests(APITestCase):
    """/products/with-price/ resolves prices per variation, not per product."""

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.other = make_organization("Other", "other")
        self.product = Product.objects.create(
            name="Sugar", organization=self.org
        )
        self.small = ProductVariation.objects.create(
            product=self.product, organization=self.org, size="s"
        )
        self.large = ProductVariation.objects.create(
            product=self.product, organization=self.org, size="l"
        )
        self.pricelist = Pricelist.objects.create(
            organization=self.org, name="Retail"
        )
        # Only the large variation is priced on this list.
        PricelistItem.objects.create(
            organization=self.org,
            pricelist=self.pricelist,
            product_variation=self.large,
            price=Decimal("180.00"),
        )

    def _get(self, query=""):
        return self.client.get(
            f"/api/products/with-price/{query}",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    def test_with_price_does_not_error_when_a_pricelist_is_supplied(self):
        """Previously raised FieldError: PricelistItem had no product_variation."""
        response = self._get(f"?pricelist_id={self.pricelist.id}")

        self.assertEqual(response.status_code, 200, response.data)

    def test_price_is_resolved_per_variation(self):
        response = self._get(f"?pricelist_id={self.pricelist.id}")

        variations = {
            v["id"]: v["price"] for v in response.data["results"][0]["variations"]
        }
        self.assertEqual(Decimal(variations[str(self.large.id)]), Decimal("180.00"))
        # The unpriced sibling must not inherit the other variation's price.
        self.assertIsNone(variations[str(self.small.id)])

    def test_without_a_pricelist_no_price_is_resolved(self):
        response = self._get()

        prices = [v["price"] for v in response.data["results"][0]["variations"]]
        self.assertEqual(prices, [None, None])

    def test_another_tenants_pricelist_id_resolves_no_price(self):
        foreign = Pricelist.objects.create(organization=self.other, name="Foreign")
        foreign_product = Product.objects.create(
            name="Flour", organization=self.other
        )
        foreign_variation = ProductVariation.objects.create(
            product=foreign_product, organization=self.other
        )
        PricelistItem.objects.create(
            organization=self.other,
            pricelist=foreign,
            product_variation=foreign_variation,
            price=Decimal("999.00"),
        )

        response = self._get(f"?pricelist_id={foreign.id}")

        prices = [v["price"] for v in response.data["results"][0]["variations"]]
        self.assertEqual(prices, [None, None])


class OrganizationBaseModelTests(APITestCase):
    """The shared base is the single definition of tenant ownership."""

    def test_every_tenanted_model_uses_the_shared_base(self):
        from organization.models import OrganizationBaseModel
        from inventory.models import InventoryItem, Location, StockMovement
        from payments.models import MpesaTransaction, Payment, Refund
        from products.models import Category, Product, ProductVariation
        from sales.models import Sale, SaleItem

        for model in (
            Category,
            Product,
            ProductVariation,
            Location,
            InventoryItem,
            StockMovement,
            Sale,
            SaleItem,
            Payment,
            MpesaTransaction,
            Refund,
            Pricelist,
            PricelistItem,
        ):
            self.assertTrue(
                issubclass(model, OrganizationBaseModel),
                f"{model.__name__} is not tenanted via OrganizationBaseModel",
            )
