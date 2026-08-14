from django.db import migrations, models


def create_default_locations(apps, schema_editor):
    """Give every organization a default location for stock to move through."""
    Organization = apps.get_model("organization", "Organization")
    Location = apps.get_model("inventory", "Location")

    for organization in Organization.objects.all():
        existing = Location.objects.filter(organization=organization)
        default = existing.filter(is_default=True).first()
        if default is not None:
            continue

        # Promote the organization's only pre-existing location rather than
        # adding a competing one.
        sole = existing.first()
        if sole is not None and existing.count() == 1:
            sole.is_default = True
            sole.save(update_fields=["is_default"])
            continue

        if sole is None:
            Location.objects.create(
                organization=organization,
                name="Main Store",
                # Location.code is globally unique, so it is scoped by slug.
                code=f"MAIN-{organization.slug}",
                is_default=True,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0001_initial"),
        ("inventory", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="is_default",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(create_default_locations, noop),
    ]
