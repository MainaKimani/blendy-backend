import django.db.models.deletion
from django.db import migrations, models


def backfill_organization(apps, schema_editor):
    """Attach existing sales to an organization.

    Sales predate tenancy, so the owning organization has to be inferred. In
    order of reliability: the products actually sold, then the recording user,
    then the sole organization if this deployment only has one.
    """
    Organization = apps.get_model("organization", "Organization")
    Sale = apps.get_model("sales", "Sale")
    SaleItem = apps.get_model("sales", "SaleItem")

    organizations = list(Organization.objects.all()[:2])
    fallback = organizations[0] if len(organizations) == 1 else None

    for sale in Sale.objects.all():
        organization_id = None

        item = SaleItem.objects.filter(sale=sale).select_related("product").first()
        if item is not None and item.product is not None:
            organization_id = item.product.organization_id

        if organization_id is None and sale.created_by_id is not None:
            organization_id = sale.created_by.organization_id

        if organization_id is None and fallback is not None:
            organization_id = fallback.id

        if organization_id is None:
            raise RuntimeError(
                f"Cannot infer organization for sale {sale.pk}. Assign one manually "
                "before running this migration."
            )

        sale.organization_id = organization_id
        sale.save(update_fields=["organization"])
        SaleItem.objects.filter(sale=sale).update(organization_id=organization_id)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0001_initial"),
        ("products", "0002_productimage_thumbnail"),
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.RunPython(backfill_organization, noop),
        migrations.AlterField(
            model_name="sale",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AlterField(
            model_name="saleitem",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
    ]
