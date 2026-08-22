"""Add the VIEWER role and enable it everywhere.

Registration (`/api/users/register/`) has always tried to assign a default role
to a self-registered user, and has always silently done nothing because no such
role existed. Seeding it makes that code do what it says.

Two steps, because either alone leaves the role invisible: `sync_rbac` creates
VIEWER globally, and `enable_default_roles` links it to organizations that were
created before it existed. A role that exists but is enabled nowhere behaves
exactly like one that was never seeded.

Both are idempotent, so this also re-applies 0002 and 0003 harmlessly for
databases that are already up to date.
"""

from django.db import migrations

from authorization.rbac import enable_default_roles, sync_rbac


def seed_viewer(apps, schema_editor):
    sync_rbac(apps)
    enable_default_roles(apps)


def unseed(apps, schema_editor):
    """Detach VIEWER from organizations, but leave the Role itself.

    Deleting the Role would cascade away any UserRoleAssignment pointing at it,
    silently removing users' role history. Withdrawing the permissions is the
    reversible part; 0002's reverse handles that.
    """
    from authorization.rbac import VIEWER

    OrganizationRole = apps.get_model("authorization", "OrganizationRole")
    OrganizationRole.objects.filter(role__name=VIEWER).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0003_backfill_organization_roles"),
    ]

    operations = [
        migrations.RunPython(seed_viewer, unseed),
    ]
