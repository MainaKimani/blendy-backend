from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase

from inventory.models import (
    InventoryItem,
    Location,
    StockMovement,
    StockTake,
    StockTakeItem,
)
from inventory.serializers import StockMovementSerializer
from inventory.services import (
    InsufficientStock,
    get_default_location,
    ledger_balance,
    record_movement,
)
from inventory.views import InventoryItemViewSet
from blendy_backend.testing import grant_role, make_organization, make_priced_variation
from organization.models import Organization
from products.models import Product, ProductVariation
from users.models import CustomUser


class OrganizationScopingTests(TestCase):
    """The shared base viewset must never return rows without a tenant."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.org = make_organization("Shop", "shop")
        self.variation = make_priced_variation(
            self.org, "Salt", Decimal("50.00")
        )
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=5,
        )

    def _queryset_for(self, organization):
        request = self.factory.get("/api/inventory/inventory-items/")
        request.organization = organization
        view = InventoryItemViewSet()
        view.request = request
        view.kwargs = {}
        return view.get_queryset()

    def test_missing_tenant_returns_no_rows(self):
        self.assertTrue(InventoryItem.objects.exists())
        self.assertEqual(self._queryset_for(None).count(), 0)

    def test_present_tenant_returns_its_own_rows(self):
        self.assertEqual(self._queryset_for(self.org).count(), 1)

    def test_other_tenant_sees_nothing(self):
        other = make_organization("Other", "other")
        self.assertEqual(self._queryset_for(other).count(), 0)


class TenantScopedSerializerTests(APITestCase):
    """organization is inferred from the request, never a required body field."""

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.other = make_organization("Other", "other")
        self.variation = make_priced_variation(
            self.org, "Salt", Decimal("50.00")
        )
        # These endpoints now require a permission, so the caller needs a role.
        # The assertion is still about the body, not about who is calling.
        self.user = CustomUser.objects.create_user(
            email="owner@shop.test", username="owner", password="pw",
            organization=self.org,
        )
        grant_role(self.user, self.org)
        self.client.force_authenticate(user=self.user)

    def _post(self, url, payload):
        return self.client.post(
            url, payload, format="json", HTTP_X_ORGANIZATION=str(self.org.id)
        )

    def test_location_create_needs_no_organization_in_the_body(self):
        response = self._post(
            "/api/inventory/locations/", {"name": "Back Room", "code": "BACK-1"}
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            Location.objects.get(code="BACK-1").organization_id, self.org.id
        )

    def test_stock_take_create_needs_no_organization_in_the_body(self):
        location = get_default_location(self.org)

        response = self._post(
            "/api/inventory/stock-takes/",
            {"reference_number": "ST-1", "location": str(location.id)},
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(StockTake.objects.get().organization_id, self.org.id)

    def test_stock_take_item_create_needs_no_organization_in_the_body(self):
        location = get_default_location(self.org)
        stock_take = StockTake.objects.create(
            organization=self.org, reference_number="ST-2", location=location
        )

        response = self._post(
            "/api/inventory/stock-take-items/",
            {
                "stock_take": str(stock_take.id),
                "product_variation": str(self.variation.id),
                "system_quantity": 10,
                "counted_quantity": 8,
                "variance": -2,
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(StockTakeItem.objects.get().organization_id, self.org.id)

    def test_stock_movement_serializer_does_not_require_organization(self):
        serializer = StockMovementSerializer(
            data={
                "product_variation": str(self.variation.id),
                "movement_type": "STOCK_IN",
                "quantity": 20,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("organization", serializer.validated_data)

    def test_stock_ledger_is_not_writable_through_the_api(self):
        """Writing here would record a movement that changes no stock level."""
        response = self._post(
            "/api/inventory/stock-movements/",
            {
                "product_variation": str(self.variation.id),
                "movement_type": "STOCK_IN",
                "quantity": 20,
            },
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_available_quantity_cannot_be_written_directly(self):
        location = get_default_location(self.org)

        response = self._post(
            "/api/inventory/inventory-items/",
            {
                "product_variation": str(self.variation.id),
                "location": str(location.id),
                "available_quantity": 99,
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        # Accepted, but the figure is ignored: stock only moves via the ledger.
        self.assertEqual(InventoryItem.objects.get().available_quantity, 0)


class StockWriteEndpointTests(APITestCase):
    """US-17 / US-19: the only supported way to put stock in or correct it."""

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.other = make_organization("Other", "other")
        self.user = CustomUser.objects.create_user(
            email="owner@shop.test", username="owner", password="pw",
            organization=self.org,
        )
        grant_role(self.user, self.org)
        self.variation = make_priced_variation(
            self.org, "Sugar", Decimal("150.00")
        )

    def _post(self, url, payload, authenticate=True):
        if authenticate:
            self.client.force_authenticate(user=self.user)
        return self.client.post(
            url, payload, format="json", HTTP_X_ORGANIZATION=str(self.org.id)
        )

    def _balance(self):
        return ledger_balance(self.org, self.variation)

    def _cached(self):
        return InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        ).available_quantity

    # --- restock (US-17) ---

    def test_restock_adds_stock_and_writes_a_ledger_entry(self):
        response = self._post(
            "/api/inventory/stock/restock/",
            {
                "product_variation": str(self.variation.id),
                "quantity": 20,
                "unit_cost": "100.00",
                "notes": "Supplier delivery",
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["available_quantity"], 20)

        movement = StockMovement.objects.get()
        self.assertEqual(movement.movement_type, "STOCK_IN")
        self.assertEqual(movement.quantity, 20)
        self.assertEqual(movement.unit_cost, Decimal("100.00"))
        self.assertEqual(movement.created_by_id, self.user.id)
        self.assertEqual(self._cached(), 20)
        self.assertEqual(self._balance(), 20)

    def test_restocked_stock_is_immediately_sellable(self):
        """The gap this closes: stock added through the API must be usable."""
        self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 5},
        )

        sale = self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {
                        "product_variation": str(self.variation.id),
                        "quantity": 2,
                        "unit_price": "150.00",
                    }
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(sale.status_code, 201, sale.data)
        self.assertEqual(self._balance(), 3)
        self.assertEqual(self._cached(), 3)

    def test_restock_requires_authentication(self):
        response = self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 5},
            authenticate=False,
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_cannot_restock_another_tenants_variation(self):
        foreign = make_priced_variation(
            self.other, "Flour", Decimal("100.00")
        )

        response = self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(foreign.id), "quantity": 5},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_restock_rejects_a_non_positive_quantity(self):
        response = self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 0},
        )

        self.assertEqual(response.status_code, 400)

    # --- adjustment (US-19) ---

    def test_adjustment_requires_a_reason(self):
        response = self._post(
            "/api/inventory/stock/adjust/",
            {"product_variation": str(self.variation.id), "quantity": -2},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reason", response.data)

    def test_delta_adjustment_records_the_reason(self):
        self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 10},
        )

        response = self._post(
            "/api/inventory/stock/adjust/",
            {
                "product_variation": str(self.variation.id),
                "quantity": -2,
                "reason": "Two bags split in transit",
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self._balance(), 8)
        movement = StockMovement.objects.get(movement_type="ADJUSTMENT")
        self.assertEqual(movement.quantity, -2)
        self.assertEqual(movement.notes, "Two bags split in transit")
        self.assertEqual(movement.created_by_id, self.user.id)

    def test_counted_quantity_records_the_difference(self):
        self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 10},
        )

        response = self._post(
            "/api/inventory/stock/adjust/",
            {
                "product_variation": str(self.variation.id),
                "counted_quantity": 7,
                "reason": "Physical count",
            },
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["available_quantity"], 7)
        movement = StockMovement.objects.get(movement_type="ADJUSTMENT")
        # The shortfall is what gets recorded, not the counted figure.
        self.assertEqual(movement.quantity, -3)
        self.assertEqual(self._cached(), 7)

    def test_a_count_that_matches_records_nothing(self):
        self._post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 10},
        )

        response = self._post(
            "/api/inventory/stock/adjust/",
            {
                "product_variation": str(self.variation.id),
                "counted_quantity": 10,
                "reason": "Physical count",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["movement"])
        self.assertFalse(
            StockMovement.objects.filter(movement_type="ADJUSTMENT").exists()
        )

    def test_delta_and_counted_quantity_are_mutually_exclusive(self):
        response = self._post(
            "/api/inventory/stock/adjust/",
            {
                "product_variation": str(self.variation.id),
                "quantity": -2,
                "counted_quantity": 7,
                "reason": "Confused",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_delta_adjustment_cannot_drive_stock_negative(self):
        response = self._post(
            "/api/inventory/stock/adjust/",
            {
                "product_variation": str(self.variation.id),
                "quantity": -5,
                "reason": "Overstated shrinkage",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient stock", str(response.data))


class LowStockAlertTests(APITestCase):
    """US-3: alert when stock reaches the threshold the owner set."""

    URL = "/api/inventory/stock/low-stock/"

    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.other = make_organization("Other", "other")
        self.user = CustomUser.objects.create_user(
            email="owner@shop.test", username="owner", password="pw",
            organization=self.org,
        )
        grant_role(self.user, self.org)

    def _variation(self, organization, name, reorder_level=None, stock=0):
        variation = make_priced_variation(
            organization, name, Decimal("150.00"), reorder_level=reorder_level
        )
        if stock:
            record_movement(
                organization=organization,
                product_variation=variation,
                movement_type="STOCK_IN",
                quantity=stock,
            )
        return variation

    def _get(self):
        self.client.force_authenticate(user=self.user)
        return self.client.get(self.URL, HTTP_X_ORGANIZATION=str(self.org.id))

    def _names(self, response):
        return [row["name"] for row in response.data["results"]]

    def test_stock_above_the_threshold_does_not_alert(self):
        self._variation(self.org, "Sugar", reorder_level=5, stock=10)

        response = self._get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 0)

    def test_stock_exactly_at_the_threshold_alerts(self):
        """MVP scenario 8: selling *down to* the threshold must fire it."""
        self._variation(self.org, "Sugar", reorder_level=5, stock=5)

        response = self._get()

        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["shortfall"], 0)

    def test_stock_below_the_threshold_alerts_with_the_shortfall(self):
        self._variation(self.org, "Sugar", reorder_level=5, stock=2)

        response = self._get()

        row = response.data["results"][0]
        self.assertEqual(row["available_quantity"], 2)
        self.assertEqual(row["reorder_level"], 5)
        self.assertEqual(row["shortfall"], 3)

    def test_variation_without_a_threshold_never_alerts(self):
        """No threshold set means there is nothing to be below."""
        self._variation(self.org, "Unwatched", reorder_level=None, stock=0)

        response = self._get()

        self.assertEqual(response.data["total_items"], 0)

    def test_selling_down_to_the_threshold_fires_the_alert(self):
        variation = self._variation(self.org, "Sugar", reorder_level=5, stock=7)
        self.assertEqual(self._get().data["total_items"], 0)

        self.client.post(
            "/api/sales/sales/",
            {
                "items": [
                    {
                        "product_variation": str(variation.id),
                        "quantity": 2,
                        "unit_price": "150.00",
                    }
                ]
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        response = self._get()
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["available_quantity"], 5)

    def test_restocking_clears_the_alert(self):
        variation = self._variation(self.org, "Sugar", reorder_level=5, stock=2)
        self.assertEqual(self._get().data["total_items"], 1)

        self.client.force_authenticate(user=self.user)
        self.client.post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(variation.id), "quantity": 20},
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(self._get().data["total_items"], 0)

    def test_most_urgent_first(self):
        self._variation(self.org, "Rice", reorder_level=10, stock=8)
        self._variation(self.org, "Sugar", reorder_level=10, stock=1)
        self._variation(self.org, "Salt", reorder_level=10, stock=4)

        names = self._names(self._get())

        self.assertEqual(
            names, ["Sugar", "Salt", "Rice"], "should be ordered by urgency"
        )

    def test_another_tenants_low_stock_is_not_listed(self):
        self._variation(self.other, "Flour", reorder_level=5, stock=0)

        response = self._get()

        self.assertEqual(response.data["total_items"], 0)

    def test_requires_authentication(self):
        self._variation(self.org, "Sugar", reorder_level=5, stock=1)

        response = self.client.get(
            self.URL, HTTP_X_ORGANIZATION=str(self.org.id)
        )

        self.assertIn(response.status_code, (401, 403))


class StockLedgerServiceTests(TestCase):
    def setUp(self):
        self.org = make_organization("Shop", "shop")
        self.variation = make_priced_variation(
            self.org, "Beans", Decimal("90.00")
        )

    def test_stock_in_then_out_leaves_a_consistent_ledger_and_cache(self):
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=20,
        )
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="SALE",
            quantity=-8,
        )

        item = InventoryItem.objects.get(
            organization=self.org, product_variation=self.variation
        )
        self.assertEqual(item.available_quantity, 12)
        self.assertEqual(ledger_balance(self.org, self.variation), 12)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_outflow_beyond_available_is_refused(self):
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=3,
        )

        with self.assertRaises(InsufficientStock):
            record_movement(
                organization=self.org,
                product_variation=self.variation,
                movement_type="SALE",
                quantity=-4,
            )

        self.assertEqual(ledger_balance(self.org, self.variation), 3)

    def test_corrections_may_go_negative_when_explicitly_allowed(self):
        record_movement(
            organization=self.org,
            product_variation=self.variation,
            movement_type="ADJUSTMENT",
            quantity=-2,
            allow_negative=True,
            notes="Shrinkage found at count",
        )

        self.assertEqual(ledger_balance(self.org, self.variation), -2)

    def test_zero_quantity_movement_is_rejected(self):
        with self.assertRaises(ValueError):
            record_movement(
                organization=self.org,
                product_variation=self.variation,
                movement_type="ADJUSTMENT",
                quantity=0,
            )

    def test_default_location_is_created_once_per_organization(self):
        first = get_default_location(self.org)
        second = get_default_location(self.org)

        self.assertEqual(first.id, second.id)
        self.assertTrue(first.is_default)
        self.assertEqual(first.code, f"MAIN-{self.org.slug}")
