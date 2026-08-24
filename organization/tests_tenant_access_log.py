"""What a shop can see about who reached into its data.

The assurance is only worth something if the shop can check it themselves,
without asking us. The care is in what it does *not* show: a refused attempt by
another customer appears, but does not name them.
"""

from rest_framework.test import APITestCase

from authorization.models import OrganizationRole, UserRoleAssignment
from authorization.rbac import CASHIER, ORG_ADMIN, PLATFORM_ADMIN, SUPPORT_AGENT
from blendy_backend.testing import make_organization
from organization.models import PlatformAccessLog
from organization.services import get_platform_organization
from users.models import CustomUser


class TenantAccessLogTests(APITestCase):
    URL = "/api/organization/access-log/"

    def setUp(self):
        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")
        self.rival = make_organization("Duka Mbili", "duka-mbili")

        self.headers = {"HTTP_X_ORGANIZATION": str(self.shop.id)}

        self.owner = self._user("owner@mama-duka.test", self.shop, ORG_ADMIN)
        self.cashier = self._user("till@mama-duka.test", self.shop, CASHIER)
        self.rival_owner = self._user("owner@duka-mbili.test", self.rival, ORG_ADMIN)
        self.agent = self._user("agent@blendy.test", self.hq, SUPPORT_AGENT)
        self.platform_admin = self._user("admin@blendy.test", self.hq, PLATFORM_ADMIN)

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

    def _as(self, user):
        self.client.force_authenticate(user=user)

    def _support_visits(self):
        self._as(self.agent)
        self.client.get("/api/sales/sales/", **self.headers)

    def _rival_probes(self):
        self._as(self.rival_owner)
        self.client.get("/api/sales/sales/", **self.headers)

    # --- the assurance itself ---------------------------------------------

    def test_an_owner_sees_blendy_looking_at_their_shop(self):
        self._support_visits()

        self._as(self.owner)
        response = self.client.get(self.URL, **self.headers)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_items"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["actor"], "agent@blendy.test")
        self.assertTrue(row["actor_is_platform"])
        self.assertEqual(row["path"], "/api/sales/sales/")
        self.assertTrue(row["granted"])

    def test_blendy_staff_are_named(self):
        """Naming the person is what makes the support relationship legible."""
        self._support_visits()

        self._as(self.owner)
        row = self.client.get(self.URL, **self.headers).data["results"][0]

        self.assertIn("@blendy.test", row["actor"])

    def test_a_refused_attempt_by_another_shop_is_shown(self):
        self._rival_probes()

        self._as(self.owner)
        response = self.client.get(self.URL, **self.headers)

        self.assertEqual(response.data["total_items"], 1)
        self.assertFalse(response.data["results"][0]["granted"])

    def test_but_the_other_shop_is_not_named(self):
        """The care in this feature.

        Naming them would hand one customer another customer's staff email —
        leaking across exactly the boundary this log exists to watch.
        """
        self._rival_probes()

        self._as(self.owner)
        row = self.client.get(self.URL, **self.headers).data["results"][0]

        self.assertNotIn("duka-mbili", row["actor"])
        self.assertNotIn("@", row["actor"])
        self.assertFalse(row["actor_is_platform"])
        self.assertEqual(row["actor"], "an account outside this organization")

    def test_the_raw_email_is_not_in_the_payload_at_all(self):
        """Not merely hidden behind a label — absent from the response."""
        self._rival_probes()

        self._as(self.owner)
        response = self.client.get(self.URL, **self.headers)

        self.assertNotIn("owner@duka-mbili.test", str(response.data))
        self.assertNotIn("actor_email", response.data["results"][0])

    # --- scoping -----------------------------------------------------------

    def test_a_shop_sees_only_its_own_rows(self):
        self._support_visits()
        self._as(self.agent)
        self.client.get(
            "/api/sales/sales/", HTTP_X_ORGANIZATION=str(self.rival.id)
        )
        self.assertEqual(PlatformAccessLog.objects.count(), 2)

        self._as(self.owner)
        response = self.client.get(self.URL, **self.headers)

        self.assertEqual(response.data["total_items"], 1)

    def test_a_shop_cannot_read_another_shops_log(self):
        self._as(self.owner)

        response = self.client.get(
            self.URL, HTTP_X_ORGANIZATION=str(self.rival.id)
        )

        self.assertEqual(response.status_code, 403)

    def test_a_members_own_traffic_never_appears(self):
        """Only crossings are recorded, so the shop's own work is not listed."""
        self._as(self.owner)
        self.client.get("/api/sales/sales/", **self.headers)

        response = self.client.get(self.URL, **self.headers)

        self.assertEqual(response.data["total_items"], 0)

    # --- who may look ------------------------------------------------------

    def test_a_cashier_cannot_read_it(self):
        """Who has been looking at the books is the owner's business."""
        self._as(self.cashier)

        self.assertEqual(
            self.client.get(self.URL, **self.headers).status_code, 403
        )

    def test_anonymous_cannot_read_it(self):
        self._as(None)

        self.assertIn(
            self.client.get(self.URL, **self.headers).status_code, (401, 403)
        )

    def test_no_tenant_header_yields_nothing(self):
        self._support_visits()
        self._as(self.owner)

        response = self.client.get(self.URL)

        self.assertIn(response.status_code, (200, 403))
        if response.status_code == 200:
            self.assertEqual(response.data["total_items"], 0)

    # --- immutability ------------------------------------------------------

    def test_a_shop_cannot_delete_its_own_log(self):
        """Convenient for a shop, and fatal to the point of the record."""
        self._support_visits()
        entry = PlatformAccessLog.objects.get()

        self._as(self.owner)
        response = self.client.delete(f"{self.URL}{entry.id}/", **self.headers)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(PlatformAccessLog.objects.filter(pk=entry.pk).exists())

    def test_a_shop_cannot_forge_an_entry(self):
        self._as(self.owner)

        response = self.client.post(
            self.URL, {"path": "/made/up/"}, format="json", **self.headers
        )

        self.assertEqual(response.status_code, 405)

    # --- the two views agree ----------------------------------------------

    def test_hq_still_sees_the_identifying_detail(self):
        """The masking is presentational; the record itself is unchanged."""
        self._rival_probes()

        self._as(self.platform_admin)
        response = self.client.get("/api/organization/platform-access-log/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["results"][0]["actor_email"], "owner@duka-mbili.test"
        )

    def test_the_superadmin_flag_counts_as_platform(self):
        """A superadmin has no organization, so membership cannot classify them."""
        root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self._as(root)
        self.client.get("/api/sales/sales/", **self.headers)

        self._as(self.owner)
        row = self.client.get(self.URL, **self.headers).data["results"][0]

        self.assertTrue(row["actor_is_platform"])
        self.assertEqual(row["actor"], "root@blendy.test")
