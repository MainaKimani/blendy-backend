from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        # Prices must be safely on the pricelist before the field is dropped.
        ("pricing", "0006_pricelist_is_default_and_seed_prices"),
        ("products", "0002_productimage_thumbnail"),
    ]

    operations = [
        migrations.RemoveField(model_name="product", name="price"),
    ]
