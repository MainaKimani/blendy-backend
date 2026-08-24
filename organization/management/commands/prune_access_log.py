"""Delete platform access records past their retention window.

There is no worker in this deployment, so this is meant for cron:

    0 3 * * 0  python manage.py prune_access_log

Two deliberate constraints, because this deletes an audit trail:

* It refuses to prune below PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS. Erasing
  the last few days is precisely what someone covering their tracks would want,
  so `--days 1` is rejected rather than obeyed.
* It reports the cutoff and the count either way, so a cron mail says what
  happened rather than only that it ran.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from organization.models import PlatformAccessLog


class Command(BaseCommand):
    help = (
        "Delete platform access log entries older than the retention window "
        "(PLATFORM_ACCESS_LOG_RETENTION_DAYS, default 365)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override the retention window for this run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted, and delete nothing.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days is None:
            days = getattr(settings, "PLATFORM_ACCESS_LOG_RETENTION_DAYS", 365)

        floor = getattr(settings, "PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS", 30)
        if days < floor:
            raise CommandError(
                f"Refusing to prune to {days} days: the minimum retention is "
                f"{floor}. An audit trail that can be trimmed to yesterday is "
                f"not one. Raise PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS if "
                f"this is genuinely intended."
            )

        cutoff = timezone.now() - timedelta(days=days)
        stale = PlatformAccessLog.objects.filter(created_at__lt=cutoff)
        count = stale.count()

        self.stdout.write(f"Retention: {days} days (cutoff {cutoff.isoformat()})")

        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} entries. Nothing was deleted.")
            return

        if count:
            stale.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {count} entries. "
                f"{PlatformAccessLog.objects.count()} remain."
            )
        )
