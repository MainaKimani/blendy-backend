from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_remove_payment_organization_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="last_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="max_retries",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="payment",
            name="next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reconciled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="reconciliation_status",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("MATCHED", "Matched"), ("MISMATCH", "Mismatch")],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="retry_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
