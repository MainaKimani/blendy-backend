"""Discovering HQ, and pruning the record of who reached into whom."""

from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from authorization.models import OrganizationRole, UserRoleAssignment
from authorization.rbac import CASHIER, ORG_ADMIN, PLATFORM_ADMIN, SUPPORT_AGENT
from blendy_backend.testing import make_organization
from organization.models import Organization, PlatformAccessLog
from organization.services import get_platform_organization
from users.models import CustomUser


class PlatformOrganizationEndpointTests(APITestCase):
    """`GET /api/organization/platform/` — HQ's id, without a shell.

    The customer listing excludes HQ on purpose, which left its id obtainable
    only from `manage.py bootstrap_hq`. Platform staff need it to send as
    X-Organization when working on HQ itself.
    """

    URL = "/api/organization/platform/"

    def setUp(self):
        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")
        self.agent = self._user("agent@blendy.test", self.hq, SUPPORT_AGENT)
        self.platform_admin = self._user("admin@blendy.test", self.hq, PLATFORM_ADMIN)
        self.owner = self._user("owner@mama-duka.test", self.shop, ORG_ADMIN)
        self.cashier = self._user("till@mama-duka.test", self.shop, CASHIER)
        self.root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )

    def _user(self, email, organization, role_name):
        user = CustomUser.objects.create_user(
            email=email, username=email, password="pw", organization=organization
        )
        UserRoleAssignment.objects.create(
            user=user,
            organization_role=OrganizationRole.objects.get(
                organization=organization, role__name=role_name
            ),
        )
        return user

    def _get(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(self.URL)

    def test_a_support_agent_can_find_hq(self):
        """Gated on any platform.* permission, not on the admin one.

        A support agent needs HQ's id as much as an admin does; gating it on
        the flag or on manage_platform_staff would send them back to the shell.
        """
        response = self._get(self.agent)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["id"], str(self.hq.id))
        self.assertTrue(response.data["is_platform"])

    def test_a_platform_admin_can_find_hq(self):
        self.assertEqual(self._get(self.platform_admin).status_code, 200)

    def test_the_superadmin_flag_works_too(self):
        self.assertEqual(self._get(self.root).status_code, 200)

    def test_a_shop_owner_cannot(self):
        """ORG_ADMIN holds all 87 tenant permissions and no platform one."""
        self.assertEqual(self._get(self.owner).status_code, 403)

    def test_a_cashier_cannot(self):
        self.assertEqual(self._get(self.cashier).status_code, 403)

    def test_anonymous_cannot(self):
        self.client.force_authenticate(user=None)

        self.assertIn(self.client.get(self.URL).status_code, (401, 403))

    def test_no_tenant_header_is_needed(self):
        """The point is to learn the id you would put in that header."""
        self.client.force_authenticate(user=self.agent)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200, response.data)

    def test_it_says_so_plainly_when_hq_is_missing(self):
        Organization.objects.filter(is_platform=True).delete()

        response = self._get(self.root)

        self.assertEqual(response.status_code, 404)
        self.assertIn("bootstrap_hq", str(response.data))

    def test_hq_is_still_absent_from_the_customer_listing(self):
        """This endpoint exists precisely because that listing excludes it."""
        self.client.force_authenticate(user=self.root)

        listing = self.client.get("/api/organization/")

        slugs = [row["slug"] for row in listing.data["results"]]
        self.assertNotIn(self.hq.slug, slugs)


class AccessLogRetentionTests(APITestCase):
    """Pruning an audit trail, with the safeguards that implies."""

    def setUp(self):
        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")

    def _entry(self, days_ago, granted=True):
        entry = PlatformAccessLog.objects.create(
            actor=None,
            actor_email="agent@blendy.test",
            organization=self.shop,
            organization_slug=self.shop.slug,
            method="GET",
            path="/api/sales/sales/",
            status_code=200 if granted else 403,
            granted=granted,
        )
        # auto_now_add ignores assignment, so write it directly.
        PlatformAccessLog.objects.filter(pk=entry.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return entry

    def test_entries_past_the_window_are_deleted(self):
        old = self._entry(400)
        recent = self._entry(10)

        call_command("prune_access_log")

        self.assertFalse(PlatformAccessLog.objects.filter(pk=old.pk).exists())
        self.assertTrue(PlatformAccessLog.objects.filter(pk=recent.pk).exists())

    def test_the_default_window_is_a_year(self):
        just_inside = self._entry(360)

        call_command("prune_access_log")

        self.assertTrue(PlatformAccessLog.objects.filter(pk=just_inside.pk).exists())

    def test_a_dry_run_deletes_nothing(self):
        self._entry(400)

        call_command("prune_access_log", dry_run=True)

        self.assertEqual(PlatformAccessLog.objects.count(), 1)

    def test_it_refuses_to_prune_below_the_floor(self):
        """The safeguard that matters.

        Trimming an audit trail to yesterday is exactly what someone covering
        their tracks would do, so a too-small window is refused rather than
        obeyed.
        """
        self._entry(5)

        with self.assertRaises(CommandError) as caught:
            call_command("prune_access_log", days=1)

        self.assertIn("minimum retention", str(caught.exception))
        self.assertEqual(PlatformAccessLog.objects.count(), 1)

    def test_the_floor_is_checked_before_anything_is_deleted(self):
        old = self._entry(400)

        with self.assertRaises(CommandError):
            call_command("prune_access_log", days=2)

        self.assertTrue(PlatformAccessLog.objects.filter(pk=old.pk).exists())

    @override_settings(PLATFORM_ACCESS_LOG_MINIMUM_RETENTION_DAYS=1)
    def test_the_floor_can_be_lowered_deliberately(self):
        """Refused by default, permitted when someone has decided to."""
        self._entry(5)

        call_command("prune_access_log", days=1)

        self.assertEqual(PlatformAccessLog.objects.count(), 0)

    @override_settings(PLATFORM_ACCESS_LOG_RETENTION_DAYS=60)
    def test_the_window_is_configurable(self):
        stale = self._entry(90)
        fresh = self._entry(30)

        call_command("prune_access_log")

        self.assertFalse(PlatformAccessLog.objects.filter(pk=stale.pk).exists())
        self.assertTrue(PlatformAccessLog.objects.filter(pk=fresh.pk).exists())

    def test_denials_are_pruned_on_the_same_schedule_as_grants(self):
        """One policy: a refused attempt is a record like any other."""
        self._entry(400, granted=False)
        self._entry(400, granted=True)

        call_command("prune_access_log")

        self.assertEqual(PlatformAccessLog.objects.count(), 0)

    def test_pruning_an_empty_log_is_harmless(self):
        call_command("prune_access_log")

        self.assertEqual(PlatformAccessLog.objects.count(), 0)
