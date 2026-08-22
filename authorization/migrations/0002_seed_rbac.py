"""Seed the permission catalogue and the built-in roles.

Nothing ever created a Permission row, so HasUserPermission matched nothing and
every guarded endpoint refused everyone — including an owner freshly onboarded
as ORG_ADMIN. This migration applies the catalogue so an existing deployment is
fixed by `migrate` alone, without a separate manual step.

The catalogue itself lives in authorization/rbac.py and will keep growing. This
migration deliberately reads the *current* catalogue rather than a snapshot of
it: seed data is not schema, and a fresh database should come up with today's
permissions, not those of the day this file was written. Re-apply after any
change with `manage.py seed_rbac`.
"""

from django.db import migrations

from authorization.rbac import sync_rbac


def seed(apps, schema_editor):
    sync_rbac(apps)


def unseed(apps, schema_editor):
    """Remove only what this migration is responsible for.

    Roles are left alone: an organization may already have enabled one and
    assigned staff to it, and deleting the Role would cascade those assignments
    away. Reversing the seed should not revoke anyone's access.
    """
    from authorization.rbac import permission_names

    Permission = apps.get_model("authorization", "Permission")
    Permission.objects.filter(name__in=permission_names()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
