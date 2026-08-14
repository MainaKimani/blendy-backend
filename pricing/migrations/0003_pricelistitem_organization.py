import django.db.models.deletion
from django.db import migrations, models


def backfill_organization(apps, schema_editor):
    """Inherit tenancy from the parent pricelist, which is already tenanted."""
    PricelistItem = apps.get_model("pricing", "PricelistItem")

    for item in PricelistItem.objects.select_related("pricelist").all():
        organization_id = item.pricelist.organization_id
        if organization_id is None:
            raise RuntimeError(
                f"Pricelist {item.pricelist_id} has no organization; cannot "
                f"tenant pricelist item {item.pk}."
            )
        item.organization_id = organization_id
        item.save(update_fields=["organization"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0002_organization_mpesa_shortcode"),
        ("pricing", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricelistitem",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.RunPython(backfill_organization, noop),
        migrations.AlterField(
            model_name="pricelistitem",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
    ]
