from django.db import migrations, models

DEFAULT_PRICELIST_NAME = "Default Pricelist"


def seed_default_pricelists(apps, schema_editor):
    """Every existing organization needs a default pricelist to keep trading.

    Except Blendy's own HQ, which never sells. Guarded rather than filtered
    unconditionally because the migration graph does not order this against the
    one that adds `is_platform` — before that field exists every organization is
    a tenant, so the filter is a no-op there.
    """
    Organization = apps.get_model("organization", "Organization")
    Pricelist = apps.get_model("pricing", "Pricelist")

    organizations = Organization.objects.all()
    if any(f.name == "is_platform" for f in Organization._meta.get_fields()):
        organizations = organizations.filter(is_platform=False)

    for organization in organizations:
        if Pricelist.objects.filter(
            organization=organization, is_default=True
        ).exists():
            continue
        Pricelist.objects.create(
            organization=organization,
            name=DEFAULT_PRICELIST_NAME,
            description="Prices used for sales unless another list applies.",
            is_default=True,
        )


def move_prices_onto_the_pricelist(apps, schema_editor):
    """Carry each variation's price over from its product, before that field goes.

    Product.price was per product, so every variation of a product inherits the
    same starting price. Owners can differentiate them afterwards; inventing a
    per-variation split here would be fabricating data.
    """
    Pricelist = apps.get_model("pricing", "Pricelist")
    PricelistItem = apps.get_model("pricing", "PricelistItem")
    ProductVariation = apps.get_model("products", "ProductVariation")

    for variation in ProductVariation.objects.select_related("product").all():
        pricelist = Pricelist.objects.filter(
            organization_id=variation.organization_id, is_default=True
        ).first()
        if pricelist is None:
            raise RuntimeError(
                f"Organization {variation.organization_id} has no default "
                "pricelist; cannot move prices onto it."
            )

        PricelistItem.objects.get_or_create(
            pricelist=pricelist,
            product_variation=variation,
            defaults={
                "organization_id": variation.organization_id,
                "price": variation.product.price,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0002_organization_mpesa_shortcode"),
        # Must run while Product.price still exists.
        ("products", "0002_productimage_thumbnail"),
        ("pricing", "0005_pricelistitem_product_variation"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricelist",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_default_pricelists, noop),
        migrations.RunPython(move_prices_onto_the_pricelist, noop),
    ]
