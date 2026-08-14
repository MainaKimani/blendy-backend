import django.db.models.deletion
from django.db import migrations, models


def backfill_organization(apps, schema_editor):
    """Derive tenancy from the sale a payment belongs to.

    Payment.sale is non-null, and sales are tenanted by the preceding sales
    migration, so every payment resolves. Transactions and refunds then inherit
    from their payment.
    """
    Payment = apps.get_model("payments", "Payment")
    MpesaTransaction = apps.get_model("payments", "MpesaTransaction")
    Refund = apps.get_model("payments", "Refund")

    for payment in Payment.objects.select_related("sale").all():
        organization_id = payment.sale.organization_id
        if organization_id is None:
            raise RuntimeError(
                f"Sale {payment.sale_id} has no organization; run the sales "
                "migration first."
            )
        payment.organization_id = organization_id
        payment.save(update_fields=["organization"])
        MpesaTransaction.objects.filter(payment=payment).update(
            organization_id=organization_id
        )
        Refund.objects.filter(payment=payment).update(organization_id=organization_id)

    orphans = MpesaTransaction.objects.filter(organization__isnull=True).count()
    if orphans:
        raise RuntimeError(
            f"{orphans} MpesaTransaction row(s) have no payment and therefore no "
            "inferable organization. Resolve them manually before migrating."
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0001_initial"),
        ("sales", "0002_sale_organization_saleitem_organization"),
        ("payments", "0003_alter_payment_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AddField(
            model_name="mpesatransaction",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AddField(
            model_name="refund",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.RunPython(backfill_organization, noop),
        migrations.AlterField(
            model_name="payment",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AlterField(
            model_name="mpesatransaction",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
        migrations.AlterField(
            model_name="refund",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="organization.organization",
            ),
        ),
    ]
