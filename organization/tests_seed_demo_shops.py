"""manage.py seed_demo_shops — two local shops, safe to re-run."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from authorization.rbac import ORG_ADMIN
from inventory.models import InventoryItem, StockMovement
from organization.models import Organization
from pricing.models import PricelistItem
from products.models import Product, ProductVariation
from users.models import CustomUser


def seed():
    call_command("seed_demo_shops", stdout=StringIO())


@override_settings(DEBUG=True)
class SeedDemoShopsTests(TestCase):
    def test_creates_both_shops_through_onboarding(self):
        seed()

        for slug, email in (
            ("blendy-studio", "admin@blendy-studio.test"),
            ("mitchy-fits", "admin@mitchy-fits.test"),
        ):
            shop = Organization.objects.get(slug=slug)
            admin = CustomUser.objects.get(email=email)
            self.assertEqual(admin.organization, shop)
            self.assertTrue(admin.check_password("blendy-dev-pass"))
            self.assertEqual(
                list(admin.role_assignments.values_list(
                    "organization_role__role__name", flat=True
                )),
                [ORG_ADMIN],
            )

    def test_every_variation_is_priced_on_its_shops_default_list(self):
        seed()

        variations = ProductVariation.objects.filter(
            organization__slug__in=["blendy-studio", "mitchy-fits"]
        )
        self.assertTrue(variations.exists())
        for variation in variations:
            item = PricelistItem.objects.get(product_variation=variation)
            self.assertTrue(item.pricelist.is_default)
            self.assertEqual(item.pricelist.organization, variation.organization)

    def test_only_the_stocked_shop_gets_opening_stock(self):
        seed()

        self.assertFalse(
            StockMovement.objects.filter(
                product_variation__organization__slug="blendy-studio"
            ).exists()
        )
        mitchy = ProductVariation.objects.filter(organization__slug="mitchy-fits")
        for variation in mitchy:
            self.assertEqual(
                InventoryItem.objects.get(product_variation=variation).available_quantity,
                20,
            )

    def test_running_twice_changes_nothing(self):
        seed()
        counts = (
            Organization.objects.count(),
            CustomUser.objects.count(),
            Product.objects.count(),
            ProductVariation.objects.count(),
            PricelistItem.objects.count(),
            StockMovement.objects.count(),
        )

        seed()

        self.assertEqual(
            counts,
            (
                Organization.objects.count(),
                CustomUser.objects.count(),
                Product.objects.count(),
                ProductVariation.objects.count(),
                PricelistItem.objects.count(),
                StockMovement.objects.count(),
            ),
        )


@override_settings(DEBUG=False)
class SeedDemoShopsSafetyTests(TestCase):
    def test_refuses_to_run_with_debug_off(self):
        with self.assertRaises(CommandError):
            seed()
        self.assertFalse(Organization.objects.filter(slug="blendy-studio").exists())
