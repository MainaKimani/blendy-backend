"""Create or adjust the platform organization, and promote staff into it."""

from django.core.management.base import BaseCommand, CommandError

from organization.services import (
    PLATFORM_NAME,
    PLATFORM_SLUG,
    create_platform_organization,
    get_platform_organization,
)
from users.models import CustomUser


class Command(BaseCommand):
    help = (
        "Ensure the platform (HQ) organization exists, optionally renaming it "
        "and moving a user into it. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument("--name", default=None, help="Rename HQ.")
        parser.add_argument("--slug", default=None, help="Re-slug HQ.")
        parser.add_argument(
            "--promote",
            default=None,
            metavar="EMAIL",
            help="Move this user into HQ. The user must already exist.",
        )

    def handle(self, *args, **options):
        organization, created = create_platform_organization(
            name=options["name"] or PLATFORM_NAME,
            slug=options["slug"] or PLATFORM_SLUG,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Created platform organization {organization.name}")
            )
        else:
            # The flag identifies HQ, not the name, so renaming is safe.
            changed = []
            if options["name"] and organization.name != options["name"]:
                organization.name = options["name"]
                changed.append("name")
            if options["slug"] and organization.slug != options["slug"]:
                organization.slug = options["slug"]
                changed.append("slug")
            if changed:
                organization.save(update_fields=changed)
                self.stdout.write(f"Updated HQ {', '.join(changed)}")
            else:
                self.stdout.write(f"Platform organization already exists: {organization.name}")

        self.stdout.write(f"  id:   {organization.id}")
        self.stdout.write(f"  slug: {organization.slug}")

        email = options["promote"]
        if not email:
            return

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist as exc:
            raise CommandError(
                f"No user with email {email}. Create them first, then re-run."
            ) from exc

        if user.organization_id == organization.id:
            self.stdout.write(f"{email} is already in HQ")
            return

        previous = user.organization
        user.organization = organization
        user.save(update_fields=["organization"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Moved {email} into HQ"
                + (f" (was in {previous.name})" if previous else " (had no organization)")
            )
        )
        self.stdout.write(
            "  Their permissions now resolve against HQ's roles. Assign one with "
            "PATCH /api/users/<id>/ {\"organization_role_ids\": [...]}."
        )
