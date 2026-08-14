from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0006_pricelist_is_default_and_seed_prices"),
        ("sales", "0005_saleitem_selling_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="pricelist",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sales",
                to="pricing.pricelist",
            ),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="cost_price",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
    ]
