"""Apply the permission catalogue in authorization/rbac.py."""

from django.core.management.base import BaseCommand

from authorization.rbac import ROLES, enable_default_roles, sync_rbac


class Command(BaseCommand):
    help = (
        "Create the RBAC permission catalogue and point each built-in role at "
        "its permissions. Idempotent — run it after changing rbac.py."
    )

    def handle(self, *args, **options):
        summary = sync_rbac()
        # A role that exists globally but is enabled for no organization looks
        # exactly like a role that was never seeded, so both halves are applied.
        enabled = enable_default_roles()

        self.stdout.write(
            "Permissions: {permissions_total} total, {permissions_created} new".format(
                **summary
            )
        )
        self.stdout.write(
            "Roles:       {roles_total} total, {roles_created} new".format(**summary)
        )
        for name, spec in ROLES.items():
            self.stdout.write(f"  {name}: {len(spec['permissions']())} permissions")
        self.stdout.write(f"Enabled {enabled} new organization/role links")
        self.stdout.write(self.style.SUCCESS("RBAC catalogue is in sync."))
