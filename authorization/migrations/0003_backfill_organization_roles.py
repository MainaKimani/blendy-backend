"""Give organizations that predate role seeding their roles back.

Seeding the catalogue (0002) fixes shops onboarded from now on, because
onboarding enables ORG_ADMIN and CASHIER as it creates them. It does nothing for
shops that already exist: they have no OrganizationRole rows, so their staff
hold no permissions no matter what the catalogue says. Left alone, an existing
owner stays locked out and the fix only appears to work on a fresh database.

This backfills both halves:

* every organization gets the built-in roles enabled;
* every user already flagged `is_organization_admin` gets the ORG_ADMIN
  assignment to match.

The second is an alignment, not an escalation: that flag is already honoured by
the IsOrgAdmin permission class, so these users could already act as admins. It
simply makes the role model agree with the flag that was standing in for it.
"""

from django.db import migrations

from authorization.rbac import ORG_ADMIN, enable_default_roles


def backfill(apps, schema_editor):
    OrganizationRole = apps.get_model("authorization", "OrganizationRole")
    Role = apps.get_model("authorization", "Role")
    UserRoleAssignment = apps.get_model("authorization", "UserRoleAssignment")
    CustomUser = apps.get_model("users", "CustomUser")

    enable_default_roles(apps)

    admin_role = Role.objects.filter(name=ORG_ADMIN).first()
    if admin_role is None:
        return

    for user in CustomUser.objects.filter(
        is_organization_admin=True, organization__isnull=False
    ):
        organization_role = OrganizationRole.objects.filter(
            organization_id=user.organization_id, role=admin_role
        ).first()
        if organization_role is None:
            continue
        UserRoleAssignment.objects.get_or_create(
            user=user, organization_role=organization_role
        )


def noop(apps, schema_editor):
    """Not reversed.

    Removing the assignments would revoke access from owners who are relying on
    it, and there is no record of which rows existed beforehand. Reversing 0002
    already withdraws the permissions themselves, which is the reversible half.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0002_seed_rbac"),
        ("organization", "0002_organization_mpesa_shortcode"),
        ("users", "0002_delete_salesagentprofile"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
