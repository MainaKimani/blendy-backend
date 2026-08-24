"""Create Blendy's own HQ organization.

Every deployment needs exactly one, and it has to exist before any platform
role can be enabled on it, so it is created here rather than left as a manual
step someone can forget.

Deliberately not created through onboarding: HQ needs no default pricelist and
no CASHIER/VIEWER roles, because it never sells anything. Rename it later with
`manage.py bootstrap_hq --name "..."` — the flag is what identifies it, not the
name, so renaming is safe.
"""

from django.db import migrations

PLATFORM_NAME = "Blendy HQ"
PLATFORM_SLUG = "blendy-hq"


def create_hq(apps, schema_editor):
    Organization = apps.get_model("organization", "Organization")

    if Organization.objects.filter(is_platform=True).exists():
        return

    # A deployment may already have an organization occupying the slug.
    slug = PLATFORM_SLUG
    suffix = 1
    while Organization.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{PLATFORM_SLUG}-{suffix}"

    name = PLATFORM_NAME
    suffix = 1
    while Organization.objects.filter(name=name).exists():
        suffix += 1
        name = f"{PLATFORM_NAME} {suffix}"

    Organization.objects.create(name=name, slug=slug, is_platform=True)


def remove_hq(apps, schema_editor):
    """Only if nothing was ever attached to it.

    Deleting an organization cascades to its users and everything they own, so
    an HQ that has staff or an access log is left in place rather than silently
    taking them with it.
    """
    Organization = apps.get_model("organization", "Organization")

    for organization in Organization.objects.filter(is_platform=True):
        if not organization.users.exists():
            organization.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0003_organization_is_platform"),
    ]

    operations = [
        migrations.RunPython(create_hq, remove_hq),
    ]
