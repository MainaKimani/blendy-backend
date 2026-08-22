"""The *_id fields on a variation must return ids.

They were declared as UUIDField(source="uom") and friends — pointing at the
related object rather than its id column. UUIDField renders with str(), so each
one returned the object's __str__ (a name) and paid a foreign-key fetch to do it.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from blendy_backend.testing import make_organization
from pricing.services import get_default_pricelist, set_price
from products.models import Currency, Product, ProductVariation, UOM
from users.models import CustomUser


class VariationIdFieldTests(APITestCase):
    def setUp(self):
        self.org = make_organization("Duka", "duka")
        self.user = CustomUser.objects.create_user(
            email="owner@duka.test", username="owner", password="pw",
            organization=self.org,
        )
        self.client.force_authenticate(user=self.user)

        self.uom = UOM.objects.create(
            name="Kilogram", symbol="kg", organization=self.org
        )
        self.currency = Currency.objects.create(
            name="Shilling", iso_code="KES", numeric_code="404", symbol="KSh",
            organization=self.org,
        )
        self.product = Product.objects.create(name="Sugar", organization=self.org)
        self.variation = ProductVariation.objects.create(
            product=self.product, organization=self.org, sku="SUG-1KG",
            uom=self.uom, currency=self.currency,
        )
        set_price(
            organization=self.org,
            pricelist=get_default_pricelist(self.org),
            product_variation=self.variation,
            price=Decimal("150.00"),
        )

    def _row(self):
        response = self.client.get(
            "/api/products/variations/", HTTP_X_ORGANIZATION=str(self.org.id)
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["results"][0]

    def test_product_id_is_an_id_not_a_name(self):
        row = self._row()

        self.assertEqual(row["product_id"], str(self.product.id))
        # The specific regression: it used to render Product.__str__.
        self.assertNotEqual(row["product_id"], self.product.name)

    def test_uom_id_is_an_id_not_a_name(self):
        row = self._row()

        self.assertEqual(row["uom_id"], str(self.uom.id))
        self.assertNotEqual(row["uom_id"], self.uom.name)

    def test_currency_id_is_an_id_not_a_name(self):
        row = self._row()

        self.assertEqual(row["currency_id"], str(self.currency.id))
        self.assertNotEqual(row["currency_id"], self.currency.name)

    def test_unset_relations_render_as_null(self):
        """uom and currency are optional, so the id fields must tolerate null."""
        ProductVariation.objects.filter(pk=self.variation.pk).update(
            uom=None, currency=None
        )

        row = self._row()

        self.assertIsNone(row["uom_id"])
        self.assertIsNone(row["currency_id"])
        self.assertEqual(row["product_id"], str(self.product.id))
