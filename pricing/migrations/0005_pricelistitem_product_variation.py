import django.db.models.deletion
from django.db import migrations, models


def backfill_product_variation(apps, schema_editor):
    """Repoint each price from its product onto that product's variation.

    Prices were keyed on Product, but the sellable unit is the variation. A
    product with exactly one variation maps unambiguously; anything else stops
    the migration rather than guessing which variation the price belonged to.
    """
    PricelistItem = apps.get_model("pricing", "PricelistItem")
    ProductVariation = apps.get_model("products", "ProductVariation")

    for item in PricelistItem.objects.all():
        variations = list(ProductVariation.objects.filter(product_id=item.product_id))

        if len(variations) != 1:
            raise RuntimeError(
                f"Cannot map pricelist item {item.pk}: product {item.product_id} "
                f"has {len(variations)} variations. Assign prices to specific "
                "variations manually before migrating."
            )

        item.product_variation = variations[0]
        item.save(update_fields=["product_variation"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_productimage_thumbnail"),
        ("pricing", "0004_alter_pricelistitem_options"),
    ]

    operations = [
        # Drop the old constraint first so the product column can be removed.
        migrations.AlterUniqueTogether(name="pricelistitem", unique_together=set()),
        migrations.AddField(
            model_name="pricelistitem",
            name="product_variation",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pricelist_items",
                to="products.productvariation",
            ),
        ),
        migrations.RunPython(backfill_product_variation, noop),
        migrations.AlterField(
            model_name="pricelistitem",
            name="product_variation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pricelist_items",
                to="products.productvariation",
            ),
        ),
        migrations.RemoveField(model_name="pricelistitem", name="product"),
        migrations.AlterUniqueTogether(
            name="pricelistitem",
            unique_together={("pricelist", "product_variation")},
        ),
    ]
