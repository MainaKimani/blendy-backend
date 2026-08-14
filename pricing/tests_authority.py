"""The pricelist is authoritative for selling prices.

Covers: onboarding seeds a default pricelist, products are created with prices
that land on that list, and a sale is priced from it — refusing to trade at all
when no price applies.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from blendy_backend.testing import make_organization, make_priced_variation
from inventory.services import record_movement
from organization.models import Organization
from pricing.models import Pricelist, PricelistItem
from pricing.services import DEFAULT_PRICELIST_NAME, get_default_pricelist, set_price
from products.models import Category, Product, ProductVariation
from sales.models import Sale
from users.models import CustomUser


class DefaultPricelistOnboardingTests(APITestCase):
    """An organization cannot trade without a pricelist, so onboarding makes one."""

    def test_onboarding_creates_the_default_pricelist(self):
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=root)

        response = self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Duka", "slug": "duka"},
                "user": {
                    "email": "owner@duka.test",
                    "username": "owner",
                    "password": "pw",
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        organization = Organization.objects.get(slug="duka")
        pricelist = get_default_pricelist(organization)
        self.assertIsNotNone(pricelist)
        self.assertEqual(pricelist.name, DEFAULT_PRICELIST_NAME)
        self.assertTrue(pricelist.is_default)


class ProductCreationPricingTests(APITestCase):
    """Prices are supplied per variation and stored on the pricelist."""

    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="owner@duka.test", username="owner", password="pw",
            organization=self.org,
        )
        self.category = Category.objects.create(name="Groceries", organization=self.org)
        self.client.force_authenticate(user=self.user)

    def _post(self, payload):
        return self.client.post(
            "/api/products/", payload, format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    def _product_payload(self, variations):
        return {
            "name": "Sugar 1kg",
            "category_id": str(self.category.id),
            "variations": variations,
        }

    def test_price_is_recorded_on_the_pricelist_not_the_variation(self):
        response = self._post(
            self._product_payload(
                [{"sku": "SUG-1KG", "cost_price": "100.00", "selling_price": "150.00"}]
            )
        )

        self.assertEqual(response.status_code, 201, response.data)
        variation = ProductVariation.objects.get(sku="SUG-1KG")

        # Cost stays on the variation; the selling price does not.
        self.assertEqual(variation.cost_price, Decimal("100.00"))
        self.assertFalse(hasattr(variation, "selling_price"))

        item = PricelistItem.objects.get(product_variation=variation)
        self.assertEqual(item.price, Decimal("150.00"))
        self.assertEqual(item.pricelist, get_default_pricelist(self.org))

    def test_product_response_no_longer_carries_a_price(self):
        response = self._post(
            self._product_payload([{"sku": "S1", "selling_price": "150.00"}])
        )

        self.assertNotIn("price", response.data)

    def test_variation_without_a_price_is_rejected(self):
        response = self._post(
            self._product_payload([{"sku": "S1", "cost_price": "100.00"}])
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(PricelistItem.objects.count(), 0)

    def test_product_with_no_variations_is_rejected(self):
        response = self._post(self._product_payload([]))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Product.objects.count(), 0)

    def test_each_variation_can_be_priced_differently(self):
        response = self._post(
            self._product_payload(
                [
                    {"sku": "SML", "size": "s", "selling_price": "150.00"},
                    {"sku": "LRG", "size": "l", "selling_price": "220.00"},
                ]
            )
        )

        self.assertEqual(response.status_code, 201, response.data)
        prices = {
            item.product_variation.sku: item.price
            for item in PricelistItem.objects.select_related("product_variation")
        }
        self.assertEqual(prices, {"SML": Decimal("150.00"), "LRG": Decimal("220.00")})

    def test_price_is_read_back_from_the_default_pricelist(self):
        self._post(self._product_payload([{"sku": "S1", "selling_price": "150.00"}]))

        listing = self.client.get(
            "/api/products/", HTTP_X_ORGANIZATION=str(self.org.id)
        )

        variation = listing.data["results"][0]["variations"][0]
        self.assertEqual(Decimal(variation["price"]), Decimal("150.00"))


class SalePricedFromPricelistTests(APITestCase):
    """A sale takes its price from the pricelist, and records which one."""

    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="owner@duka.test", username="owner", password="pw",
            organization=self.org,
        )
        self.variation = make_priced_variation(
            self.org, "Sugar", Decimal("150.00"), cost=Decimal("100.00")
        )
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=50,
        )

    def _sell(self, quantity=1, unit_price="150.00", variation=None):
        line = {
            "product_variation": str((variation or self.variation).id),
            "quantity": quantity,
        }
        if unit_price is not None:
            line["unit_price"] = unit_price
        return self.client.post(
            "/api/sales/sales/", {"items": [line]}, format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    def test_sale_is_priced_from_the_pricelist(self):
        response = self._sell(quantity=2)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("300.00"))

    def test_sale_records_the_pricelist_it_used(self):
        response = self._sell()

        sale = Sale.objects.get(id=response.data["id"])
        self.assertEqual(sale.pricelist, get_default_pricelist(self.org))

    def test_sale_snapshots_the_cost_price(self):
        response = self._sell()

        item = Sale.objects.get(id=response.data["id"]).items.get()
        self.assertEqual(item.cost_price, Decimal("100.00"))
        self.assertEqual(item.unit_price, Decimal("150.00"))

    def test_price_submitted_against_the_pricelist_must_match(self):
        response = self._sell(unit_price="1.00")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Default Pricelist", str(response.data))
        self.assertEqual(Sale.objects.count(), 0)

    def test_omitted_price_defaults_to_the_pricelist_price(self):
        response = self._sell(unit_price=None)

        self.assertEqual(response.status_code, 201, response.data)
        item = Sale.objects.get(id=response.data["id"]).items.get()
        self.assertEqual(item.unit_price, Decimal("150.00"))

    def test_unpriced_variation_cannot_be_sold(self):
        product = Product.objects.create(name="Unpriced", organization=self.org)
        unpriced = ProductVariation.objects.create(
            product=product, organization=self.org
        )
        record_movement(
            organization=self.org,
            product_variation=unpriced,
            movement_type="STOCK_IN",
            quantity=10,
        )

        response = self._sell(variation=unpriced, unit_price="50.00")

        self.assertEqual(response.status_code, 400)
        self.assertIn("no price", str(response.data))
        self.assertEqual(Sale.objects.count(), 0)

    def test_organization_without_a_pricelist_cannot_sell(self):
        """Without a pricelist, no transaction should happen."""
        Pricelist.objects.filter(organization=self.org).delete()

        response = self._sell()

        self.assertEqual(response.status_code, 400)
        self.assertIn("no active default pricelist", str(response.data))
        self.assertEqual(Sale.objects.count(), 0)

    def test_a_later_price_change_does_not_rewrite_a_past_sale(self):
        """The whole point of snapshotting: history survives repricing."""
        response = self._sell(quantity=2)
        sale_id = response.data["id"]

        set_price(
            organization=self.org,
            pricelist=get_default_pricelist(self.org),
            product_variation=self.variation,
            price=Decimal("999.00"),
        )
        self.variation.cost_price = Decimal("500.00")
        self.variation.save(update_fields=["cost_price"])

        item = Sale.objects.get(id=sale_id).items.get()
        self.assertEqual(item.unit_price, Decimal("150.00"))
        self.assertEqual(item.cost_price, Decimal("100.00"))
        self.assertEqual(item.total_price, Decimal("300.00"))
