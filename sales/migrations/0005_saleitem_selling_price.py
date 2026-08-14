from decimal import Decimal

from django.db import migrations, models


def backfill_selling_price(apps, schema_editor):
    """Derive what each existing line actually charged.

    Discount was previously a per-line amount; it is now per unit. Historic rows
    all carry discount 0, so the two readings coincide and selling_price is just
    the unit price. A non-zero legacy discount cannot be reinterpreted safely,
    so it stops the migration rather than silently changing what a line means.
    """
    SaleItem = apps.get_model("sales", "SaleItem")

    ambiguous = SaleItem.objects.exclude(discount=Decimal("0.00")).count()
    if ambiguous:
        raise RuntimeError(
            f"{ambiguous} sale item(s) carry a per-line discount that cannot be "
            "automatically reinterpreted as a per-unit discount. Resolve them "
            "manually before migrating."
        )

    SaleItem.objects.all().update(selling_price=models.F("unit_price"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0004_alter_sale_options_alter_sale_payment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="selling_price",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
        migrations.RunPython(backfill_selling_price, noop),
    ]
