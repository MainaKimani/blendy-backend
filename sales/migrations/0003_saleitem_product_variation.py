import django.db.models.deletion
from django.db import migrations, models


def backfill_product_variation(apps, schema_editor):
    """Map each existing sale line from (product, size) onto a real variation.

    Sale lines used to point at a Product plus a loose size string. Prefer the
    variation whose size matches; otherwise fall back to the product's only
    variation. Anything ambiguous stops the migration rather than guessing.
    """
    SaleItem = apps.get_model("sales", "SaleItem")
    ProductVariation = apps.get_model("products", "ProductVariation")

    for item in SaleItem.objects.select_related("product").all():
        variations = ProductVariation.objects.filter(product=item.product)

        match = None
        if item.size_variation:
            match = variations.filter(size=item.size_variation).first()
        if match is None and variations.count() == 1:
            match = variations.first()

        if match is None:
            raise RuntimeError(
                f"Cannot map sale item {item.pk} (product={item.product_id}, "
                f"size={item.size_variation!r}) onto a ProductVariation. "
                "Resolve it manually before migrating."
            )

        item.product_variation = match
        item.save(update_fields=["product_variation"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_productimage_thumbnail"),
        ("sales", "0002_sale_organization_saleitem_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="product_variation",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_items",
                to="products.productvariation",
            ),
        ),
        migrations.RunPython(backfill_product_variation, noop),
        migrations.AlterField(
            model_name="saleitem",
            name="product_variation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_items",
                to="products.productvariation",
            ),
        ),
        migrations.RemoveField(model_name="saleitem", name="product"),
        migrations.RemoveField(model_name="saleitem", name="size_variation"),
    ]
