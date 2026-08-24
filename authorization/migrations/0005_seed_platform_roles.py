"""Seed the platform permissions and roles, and enable them on HQ.

Depends on the migration that creates the HQ organization, so both the
`is_platform` column and the row itself exist by the time this runs.

`sync_rbac` is re-applied here because the catalogue has grown: the `platform.*`
permissions are new, and PLATFORM_ADMIN / SUPPORT_AGENT need their permission
sets written. It is idempotent, so re-applying the earlier seeds costs nothing.

Note that ORG_ADMIN is derived from the *tenant* pool only. If it were derived
from the whole catalogue, this migration would silently hand every shop owner
`platform.access_tenants` and with it the ability to read every other shop.
"""

from django.db import migrations

from authorization.rbac import enable_platform_roles, sync_rbac


def seed(apps, schema_editor):
    sync_rbac(apps)
    enable_platform_roles(apps)


def unseed(apps, schema_editor):
    """Remove the platform permissions and detach the platform roles.

    The Role rows themselves are left, as elsewhere: deleting one cascades to
    every UserRoleAssignment pointing at it, which would silently erase who held
    what.
    """
    from authorization.rbac import PLATFORM_ROLES, platform_permission_names

    OrganizationRole = apps.get_model("authorization", "OrganizationRole")
    Permission = apps.get_model("authorization", "Permission")

    OrganizationRole.objects.filter(role__name__in=PLATFORM_ROLES).delete()
    Permission.objects.filter(name__in=platform_permission_names()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0004_seed_viewer_role"),
        ("organization", "0004_create_platform_organization"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
