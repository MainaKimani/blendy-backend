"""Seed two local shops whose needs differ: one made to order, one stocked.

Online-shop features are meant to be general, so they are checked against two
shops that sell very differently:

- **Blendy Studio:** canvas art prints, printed after ordering, so there is no
  stock to count.
- **Mitchy Fits:** activewear, held in stock in sizes and colours.

Variations can't yet express a print's size and finish, because they only have
a fixed clothing size and a free-text colour. Until shops can define their own
options, each artwork gets a single variation at the smallest print's price
and no size data, so nothing here has to be undone when options arrive.
Delivery zones aren't seeded because shops can't configure delivery yet.

Shops are created through the same serializer as the onboarding endpoint, so
they get the default pricelist, roles and admin user that real shops get.
"""

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventory.services import record_movement
from organization.models import Organization
from organization.serializers import OnboardOrganizationSerializer
from pricing.services import require_default_pricelist, set_price
from products.models import Category, Product, ProductVariation

# Local only: the command refuses to run unless DEBUG is on.
DEV_PASSWORD = "blendy-dev-pass"

OPENING_STOCK = 20

SHOPS = [
    {
        "organization": {
            "name": "Blendy Studio",
            "slug": "blendy-studio",
            "business_type": "Art prints",
            "contact_phone": "+254748774164",
            "address": "Nairobi, Kenya",
        },
        "admin": {
            "email": "admin@blendy-studio.test",
            "username": "blendy-studio-admin",
            "first_name": "Blendy",
            "last_name": "Admin",
        },
        "stocked": False,
        "category": "Canvas prints",
        "products": [
            # Price is the 30 × 42 cm stretched canvas, the smallest print.
            {"key": "sand-dunes", "name": "Sand Dunes", "tags": "abstract,minimalist",
             "variations": [{"price": "2500"}]},
            {"key": "kintsugi-bowl", "name": "Kintsugi Bowl", "tags": "kintsugi",
             "variations": [{"price": "2500"}]},
            {"key": "starry-night", "name": "The Starry Night (Van Gogh)",
             "tags": "van-gogh,reproduction", "variations": [{"price": "2500"}]},
            {"key": "terracotta-arches", "name": "Terracotta Arches",
             "tags": "abstract,minimalist", "variations": [{"price": "2500"}]},
        ],
    },
    {
        "organization": {
            "name": "Mitchy Fits",
            "slug": "mitchy-fits",
            "business_type": "Activewear",
            "address": "Nairobi, Kenya",
        },
        "admin": {
            "email": "admin@mitchy-fits.test",
            "username": "mitchy-fits-admin",
            "first_name": "Mitchy",
            "last_name": "Admin",
        },
        "stocked": True,
        "category": "Activewear",
        "products": [
            {"key": "leggings", "name": "High-Waist Leggings", "tags": "gym,bottoms",
             "variations": [
                 {"size": size, "color": color, "price": "2800", "cost": "1400"}
                 for size in ("s", "m", "l") for color in ("Black", "Olive")
             ]},
            {"key": "sports-bra", "name": "Seamless Sports Bra", "tags": "gym,tops",
             "variations": [
                 {"size": size, "color": "Black", "price": "1800", "cost": "900"}
                 for size in ("s", "m", "l")
             ]},
            {"key": "hoodie", "name": "Oversized Hoodie", "tags": "outerwear",
             "variations": [
                 {"size": size, "color": "Grey", "price": "3500", "cost": "1900"}
                 for size in ("m", "l", "xl")
             ]},
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Create the Blendy Studio and Mitchy Fits demo shops with an admin, a "
        "category and a few priced products each. Local use only. Idempotent."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to run with DEBUG off: this creates admin users with a "
                "published password."
            )

        for shop in SHOPS:
            organization = self.ensure_shop(shop)
            self.ensure_catalogue(organization, shop)

        self.stdout.write(f"\nAdmin password for both shops: {DEV_PASSWORD}")

    def ensure_shop(self, shop):
        org_data = shop["organization"]
        organization = Organization.objects.filter(slug=org_data["slug"]).first()
        if organization is not None:
            self.stdout.write(f"{organization.name} already exists, kept as is")
        else:
            serializer = OnboardOrganizationSerializer(
                data={
                    "organization": org_data,
                    "user": {**shop["admin"], "password": DEV_PASSWORD},
                }
            )
            if not serializer.is_valid():
                raise CommandError(
                    f"Could not onboard {org_data['name']}: {serializer.errors}"
                )
            organization = serializer.save()["organization"]
            self.stdout.write(self.style.SUCCESS(f"Onboarded {organization.name}"))

        self.stdout.write(f"  id:    {organization.id}")
        self.stdout.write(f"  admin: {shop['admin']['email']}")
        return organization

    @transaction.atomic
    def ensure_catalogue(self, organization, shop):
        pricelist = require_default_pricelist(organization)
        category, _ = Category.objects.get_or_create(
            organization=organization, name=shop["category"]
        )

        added = 0
        for product_data in shop["products"]:
            # SKUs are unique across all shops, hence the slug prefix. They are
            # also what makes a re-run find the rows it made last time.
            product_sku = f"{organization.slug}-{product_data['key']}"
            product, _ = Product.objects.get_or_create(
                sku=product_sku,
                defaults={
                    "organization": organization,
                    "name": product_data["name"],
                    "tags": product_data["tags"],
                    "category": category,
                },
            )

            for variation_data in product_data["variations"]:
                suffix = "-".join(
                    part.lower()
                    for part in (variation_data.get("size"), variation_data.get("color"))
                    if part
                ) or "default"
                variation, created = ProductVariation.objects.get_or_create(
                    sku=f"{product_sku}-{suffix}",
                    defaults={
                        "organization": organization,
                        "product": product,
                        "size": variation_data.get("size"),
                        "color": variation_data.get("color", ""),
                        "cost_price": Decimal(variation_data.get("cost", "0")),
                    },
                )
                if not created:
                    continue

                set_price(
                    organization=organization,
                    pricelist=pricelist,
                    product_variation=variation,
                    price=Decimal(variation_data["price"]),
                )
                # Opening stock goes in once, when the variation is first made,
                # so a re-run doesn't add it again.
                if shop["stocked"]:
                    record_movement(
                        organization=organization,
                        product_variation=variation,
                        movement_type="STOCK_IN",
                        quantity=OPENING_STOCK,
                        reference_number="SEED",
                        notes="Opening stock from seed_demo_shops",
                    )
                added += 1

        self.stdout.write(f"  {added} variation(s) added to {category.name}")
