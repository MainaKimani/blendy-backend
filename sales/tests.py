from decimal import Decimal

from rest_framework.test import APITestCase

from inventory.models import InventoryItem, StockMovement
from inventory.services import get_default_location, ledger_balance, record_movement
from blendy_backend.testing import grant_role, make_organization, make_priced_variation
from organization.models import Organization
from products.models import Product, ProductVariation
from sales.models import Sale, SaleItem
from users.models import CustomUser


class SaleTestData:
    """Shared fixture helpers for the sale flow."""

    def make_variation(self, organization, name, price, stock=0, cost=Decimal("0.00")):
        variation = make_priced_variation(organization, name, price, cost=cost)
        if stock:
            record_movement(
                organization=organization,
                product_variation=variation,
                movement_type="STOCK_IN",
                quantity=stock,
                notes="Opening stock",
            )
        return variation


class SaleTenantIsolationTests(APITestCase, SaleTestData):
    """Sales must never leak across organizations, including to anonymous callers."""

    def setUp(self):
        self.org_a = make_organization("Shop A", "shop-a")
        self.org_b = make_organization("Shop B", "shop-b")

        self.user_a = CustomUser.objects.create_user(
            email="a@shop.test", username="a", password="pw", organization=self.org_a
        )
        grant_role(self.user_a, self.org_a)

        self.variation_a = self.make_variation(
            self.org_a, "Sugar", Decimal("150.00"), stock=10
        )
        self.variation_b = self.make_variation(
            self.org_b, "Flour", Decimal("200.00"), stock=10
        )

        self.sale_a = self._make_sale(self.org_a, self.variation_a, Decimal("150.00"))
        self.sale_b = self._make_sale(self.org_b, self.variation_b, Decimal("200.00"))

    def _make_sale(self, organization, variation, price):
        sale = Sale.objects.create(organization=organization)
        SaleItem.objects.create(
            sale=sale,
            organization=organization,
            product_variation=variation,
            quantity=1,
            unit_price=price,
            selling_price=price,
            total_price=price,
        )
        return sale

    def test_anonymous_cannot_list_sales(self):
        response = self.client.get("/api/sales/sales/")

        self.assertIn(response.status_code, (401, 403))

    def test_sale_list_without_tenant_header_is_refused(self):
        """Fail closed: a missing tenant header must not mean 'every tenant'."""
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get("/api/sales/sales/")

        self.assertEqual(response.status_code, 403)

    def test_sale_list_is_scoped_to_the_requested_tenant(self):
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            "/api/sales/sales/", HTTP_X_ORGANIZATION=str(self.org_a.id)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.sale_a.id))

    def test_other_tenants_sale_is_not_retrievable_by_id(self):
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            f"/api/sales/sales/{self.sale_b.id}/",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_borrow_another_tenants_header(self):
        """The header alone must not grant access to a tenant you don't belong to."""
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            "/api/sales/sales/", HTTP_X_ORGANIZATION=str(self.org_b.id)
        )

        self.assertEqual(response.status_code, 403)

    def test_sale_creation_without_tenant_header_is_rejected(self):
        payload = {
            "items": [
                {
                    "product_variation": str(self.variation_a.id),
                    "quantity": 1,
                    "unit_price": "150.00",
                }
            ]
        }

        response = self.client.post("/api/sales/sales/", payload, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Sale.objects.count(), 2)

    def test_created_sale_and_items_inherit_the_tenant(self):
        payload = {
            "items": [
                {
                    "product_variation": str(self.variation_a.id),
                    "quantity": 2,
                    "unit_price": "150.00",
                }
            ]
        }

        response = self.client.post(
            "/api/sales/sales/",
            payload,
            format="json",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 201)
        sale = Sale.objects.get(id=response.data["id"])
        self.assertEqual(sale.organization_id, self.org_a.id)
        self.assertEqual(
            list(sale.items.values_list("organization_id", flat=True)),
            [self.org_a.id],
        )

    def test_cannot_sell_another_tenants_variation(self):
        payload = {
            "items": [
                {
                    "product_variation": str(self.variation_b.id),
                    "quantity": 1,
                    "unit_price": "200.00",
                }
            ]
        }

        response = self.client.post(
            "/api/sales/sales/",
            payload,
            format="json",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 400)


class SalePriceValidationTests(APITestCase, SaleTestData):
    """Prices are verified server-side; a caller cannot name its own price."""

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.staff = CustomUser.objects.create_user(
            email="till@shop.test", username="till", password="pw",
            organization=self.org,
        )
        grant_role(self.staff, self.org)
        # Catalogue price is 150.00.
        self.variation = self.make_variation(
            self.org, "Sugar", Decimal("150.00"), stock=50
        )

    def _post(self, line, authenticated=False):
        if authenticated:
            self.client.force_authenticate(user=self.staff)
        return self.client.post(
            "/api/sales/sales/",
            {"items": [{"product_variation": str(self.variation.id), **line}]},
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    def test_anonymous_caller_cannot_undercut_the_catalogue_price(self):
        response = self._post({"quantity": 1, "unit_price": "1.00"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match the price", str(response.data))
        self.assertEqual(Sale.objects.count(), 0)

    def test_anonymous_caller_cannot_submit_a_zero_price(self):
        response = self._post({"quantity": 1, "unit_price": "0.00"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_anonymous_caller_cannot_zero_the_line_via_discount(self):
        """The discount field must not be a second route to a free sale."""
        response = self._post(
            {"quantity": 1, "unit_price": "150.00", "discount": "150.00"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("signed-in user", str(response.data))
        self.assertEqual(Sale.objects.count(), 0)

    def test_selling_price_inconsistent_with_discount_is_rejected(self):
        response = self._post(
            {
                "quantity": 1,
                "unit_price": "150.00",
                "discount": "10.00",
                "selling_price": "50.00",
            },
            authenticated=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not equal unit_price", str(response.data))

    def test_discount_larger_than_the_unit_price_is_rejected(self):
        response = self._post(
            {"quantity": 1, "unit_price": "150.00", "discount": "200.00"},
            authenticated=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("exceeds the unit price", str(response.data))

    def test_matching_price_is_accepted_and_all_three_fields_recorded(self):
        response = self._post({"quantity": 2, "unit_price": "150.00"})

        self.assertEqual(response.status_code, 201, response.data)
        item = Sale.objects.get(id=response.data["id"]).items.get()
        self.assertEqual(item.unit_price, Decimal("150.00"))
        self.assertEqual(item.discount, Decimal("0.00"))
        self.assertEqual(item.selling_price, Decimal("150.00"))
        self.assertEqual(item.total_price, Decimal("300.00"))

    def test_staff_may_discount_and_the_concession_is_recorded(self):
        response = self._post(
            {
                "quantity": 3,
                "unit_price": "150.00",
                "discount": "10.00",
                "selling_price": "140.00",
            },
            authenticated=True,
        )

        self.assertEqual(response.status_code, 201, response.data)
        item = Sale.objects.get(id=response.data["id"]).items.get()
        self.assertEqual(item.unit_price, Decimal("150.00"))
        self.assertEqual(item.discount, Decimal("10.00"))
        self.assertEqual(item.selling_price, Decimal("140.00"))
        self.assertEqual(item.total_price, Decimal("420.00"))
        self.assertEqual(
            Sale.objects.get(id=response.data["id"]).total_amount, Decimal("420.00")
        )

    def test_omitted_prices_default_to_the_catalogue(self):
        response = self._post({"quantity": 1})

        self.assertEqual(response.status_code, 201, response.data)
        item = Sale.objects.get(id=response.data["id"]).items.get()
        self.assertEqual(item.unit_price, Decimal("150.00"))
        self.assertEqual(item.selling_price, Decimal("150.00"))

    def test_price_validation_also_applies_when_editing_a_sale(self):
        created = self._post({"quantity": 1, "unit_price": "150.00"})
        self.client.force_authenticate(user=self.staff)

        response = self.client.patch(
            f"/api/sales/sales/{created.data['id']}/",
            {
                "items": [
                    {
                        "product_variation": str(self.variation.id),
                        "quantity": 1,
                        "unit_price": "1.00",
                    }
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match the price", str(response.data))


class SaleStockLedgerTests(APITestCase, SaleTestData):
    """US-2 / US-18: a sale decrements stock through the append-only ledger."""

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.user = CustomUser.objects.create_user(
            email="owner@shop.test", username="owner", password="pw",
            organization=self.org,
        )
        grant_role(self.user, self.org)
        self.variation = self.make_variation(
            self.org, "Maize Flour", Decimal("120.00"), stock=10
        )

    def _post_sale(self, quantity):
        return self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {
                        "product_variation": str(self.variation.id),
                        "quantity": quantity,
                        "unit_price": "120.00",
                    }
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    def test_sale_decrements_stock_and_writes_a_ledger_entry(self):
        response = self._post_sale(3)
        self.assertEqual(response.status_code, 201)

        item = InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        )
        self.assertEqual(item.available_quantity, 7)

        movement = StockMovement.objects.get(movement_type="SALE")
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(movement.reference_number, str(response.data["id"]))
        self.assertEqual(movement.organization_id, self.org.id)

    def test_cached_balance_matches_the_ledger_sum(self):
        self._post_sale(3)
        self._post_sale(2)

        item = InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        )
        self.assertEqual(
            item.available_quantity,
            ledger_balance(self.org, self.variation),
        )
        self.assertEqual(item.available_quantity, 5)

    def test_sale_beyond_available_stock_is_rejected(self):
        response = self._post_sale(11)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        # The whole sale rolls back, so no partial ledger entry survives.
        self.assertFalse(StockMovement.objects.filter(movement_type="SALE").exists())
        item = InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        )
        self.assertEqual(item.available_quantity, 10)

    def test_multi_item_sale_decrements_every_line(self):
        second = self.make_variation(self.org, "Rice", Decimal("200.00"), stock=4)

        response = self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {
                        "product_variation": str(self.variation.id),
                        "quantity": 2,
                        "unit_price": "120.00",
                    },
                    {
                        "product_variation": str(second.id),
                        "quantity": 1,
                        "unit_price": "200.00",
                    },
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ledger_balance(self.org, self.variation), 8)
        self.assertEqual(ledger_balance(self.org, second), 3)

    def test_stock_moves_through_the_default_location(self):
        self._post_sale(1)

        location = get_default_location(self.org)
        self.assertTrue(location.is_default)
        self.assertEqual(
            StockMovement.objects.get(movement_type="SALE").location_id, location.id
        )

    def test_editing_a_sale_returns_the_previous_lines_stock(self):
        response = self._post_sale(3)
        sale_id = response.data["id"]
        self.assertEqual(ledger_balance(self.org, self.variation), 7)

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/sales/sales/{sale_id}/",
            {
                "items": [
                    {
                        "product_variation": str(self.variation.id),
                        "quantity": 1,
                        "unit_price": "120.00",
                    }
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 200)
        # 10 - 3 (original) + 3 (reversal) - 1 (new line) = 9
        self.assertEqual(ledger_balance(self.org, self.variation), 9)
        item = InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        )
        self.assertEqual(item.available_quantity, 9)
