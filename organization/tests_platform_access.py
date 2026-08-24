"""Cross-tenant access, and the record it leaves.

This is the change that relaxes the tenant boundary earlier work was spent
tightening, so it is tested from every direction: who may cross, what they may
do once across, who may not, and what is written down either way.
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from authorization.models import OrganizationRole, UserRoleAssignment
from authorization.rbac import (
    CASHIER,
    ORG_ADMIN,
    PLATFORM_ADMIN,
    SUPPORT_AGENT,
)
from blendy_backend.testing import make_organization, make_priced_variation
from inventory.services import record_movement
from organization.models import PlatformAccessLog
from organization.services import get_platform_organization
from users.models import CustomUser


class CrossTenantBase(APITestCase):
    def setUp(self):
        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")
        self.other_shop = make_organization("Duka Mbili", "duka-mbili")
        self.headers = {"HTTP_X_ORGANIZATION": str(self.shop.id)}

        self.owner = self._user("owner@mama-duka.test", self.shop, ORG_ADMIN)
        self.cashier = self._user("till@mama-duka.test", self.shop, CASHIER)
        self.outsider = self._user("owner@duka-mbili.test", self.other_shop, ORG_ADMIN)
        self.agent = self._user("agent@blendy.test", self.hq, SUPPORT_AGENT)
        self.platform_admin = self._user("admin@blendy.test", self.hq, PLATFORM_ADMIN)
        self.root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )

        self.variation = make_priced_variation(
            self.shop, "Sugar", Decimal("165.00"), cost=Decimal("120.00")
        )
        record_movement(
            organization=self.shop,
            product_variation=self.variation,
            movement_type="STOCK_IN",
            quantity=50,
        )

    def _user(self, email, organization, role_name):
        # Username is the whole email: two shops both have an "owner@".
        user = CustomUser.objects.create_user(
            email=email, username=email, password="pw",
            organization=organization,
        )
        UserRoleAssignment.objects.create(
            user=user,
            organization_role=OrganizationRole.objects.get(
                organization=organization, role__name=role_name
            ),
        )
        return user

    def _get(self, user, url="/api/sales/sales/"):
        self.client.force_authenticate(user=user)
        return self.client.get(url, **self.headers)

    def _write(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post(
            "/api/inventory/stock/restock/",
            {"product_variation": str(self.variation.id), "quantity": 5},
            format="json",
            **self.headers,
        )


class WhoMayCrossTests(CrossTenantBase):
    """The matrix. Every row is a different reason to be allowed or refused."""

    def test_a_member_reads_their_own_shop(self):
        self.assertEqual(self._get(self.owner).status_code, 200)

    def test_support_may_read_another_shop(self):
        """The whole point: we can now help a shop that calls us."""
        response = self._get(self.agent)

        self.assertEqual(response.status_code, 200, response.data)

    def test_support_may_not_write_to_another_shop(self):
        """access_tenants is a read grant; writing needs act_as_tenant."""
        self.assertEqual(self._write(self.agent).status_code, 403)

    def test_a_platform_admin_may_write_to_another_shop(self):
        response = self._write(self.platform_admin)

        self.assertEqual(response.status_code, 201, response.data)

    def test_the_superadmin_flag_still_opens_everything(self):
        """Break-glass is retained deliberately."""
        self.assertEqual(self._get(self.root).status_code, 200)
        self.assertEqual(self._write(self.root).status_code, 201)

    def test_one_shop_still_cannot_read_another(self):
        """The boundary this change relaxes must stay shut for tenants."""
        self.assertEqual(self._get(self.outsider).status_code, 403)

    def test_a_cashier_cannot_reach_another_shop(self):
        self.client.force_authenticate(user=self.cashier)

        response = self.client.get(
            "/api/sales/sales/", HTTP_X_ORGANIZATION=str(self.other_shop.id)
        )

        self.assertEqual(response.status_code, 403)

    def test_no_tenant_header_is_still_refused(self):
        """Fail closed: platform staff must name the shop they are entering."""
        self.client.force_authenticate(user=self.agent)

        response = self.client.get("/api/sales/sales/")

        self.assertEqual(response.status_code, 403)

    def test_anonymous_gains_nothing(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/sales/sales/", **self.headers)

        self.assertIn(response.status_code, (401, 403))


class WhatSupportSeesTests(CrossTenantBase):
    """Once across, the ordinary per-model permissions still apply."""

    def test_support_reads_the_things_a_shop_calls_about(self):
        for url in [
            "/api/sales/sales/",
            "/api/payments/payments/",
            "/api/inventory/inventory-items/",
            "/api/inventory/stock/low-stock/",
            "/api/pricing/pricelist-items/",
            "/api/products/variations/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self._get(self.agent, url).status_code, 200)

    def test_support_is_refused_every_write(self):
        self.client.force_authenticate(user=self.agent)

        attempts = [
            ("/api/pricing/pricelists/", {"name": "Cheap"}),
            ("/api/inventory/stock/adjust/", {
                "product_variation": str(self.variation.id),
                "quantity": -1, "reason": "x"}),
            ("/api/inventory/stock/restock/", {
                "product_variation": str(self.variation.id), "quantity": 5}),
            ("/api/products/categories/", {"name": "Sneaky"}),
        ]
        for url, body in attempts:
            with self.subTest(url=url):
                response = self.client.post(url, body, format="json", **self.headers)
                self.assertEqual(response.status_code, 403, response.data)

    def test_creating_a_sale_is_open_to_everyone_including_support(self):
        """Not an exception carved out for platform staff.

        POST /api/sales/sales/ is AllowAny so that a walk-in customer can check
        out without an account, which means it never consults
        IsOrganizationUser and so is not gated by act_as_tenant either. A
        support agent has exactly the power an anonymous caller already has —
        no more — and unlike an anonymous caller, their request is logged.
        """
        self.client.force_authenticate(user=self.agent)

        response = self.client.post(
            "/api/sales/sales/",
            {"items": [{"product_variation": str(self.variation.id), "quantity": 1}]},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            PlatformAccessLog.objects.filter(
                actor=self.agent, path="/api/sales/sales/", granted=True
            ).exists()
        )

    def test_support_sees_the_shops_own_rows_not_another_shops(self):
        """Crossing in means acting as that tenant, not seeing everything."""
        other_variation = make_priced_variation(
            self.other_shop, "Flour", Decimal("90.00")
        )

        response = self._get(self.agent, "/api/products/variations/")

        ids = [row["id"] for row in response.data["results"]]
        self.assertIn(str(self.variation.id), ids)
        self.assertNotIn(str(other_variation.id), ids)


class AccessIsRecordedTests(CrossTenantBase):
    """Whatever the outcome, crossing the boundary leaves a record."""

    def test_a_members_own_request_is_not_logged(self):
        """Logging ordinary traffic would bury the rows that matter."""
        self._get(self.owner)

        self.assertEqual(PlatformAccessLog.objects.count(), 0)

    def test_a_granted_cross_tenant_read_is_logged(self):
        self._get(self.agent)

        entry = PlatformAccessLog.objects.get()
        self.assertEqual(entry.actor, self.agent)
        self.assertEqual(entry.actor_email, "agent@blendy.test")
        self.assertEqual(entry.organization, self.shop)
        self.assertEqual(entry.organization_slug, "mama-duka")
        self.assertEqual(entry.method, "GET")
        self.assertEqual(entry.path, "/api/sales/sales/")
        self.assertEqual(entry.status_code, 200)
        self.assertTrue(entry.granted)

    def test_a_refused_write_is_logged_too(self):
        """A refusal is as worth knowing as a success."""
        self._write(self.agent)

        entry = PlatformAccessLog.objects.get()
        self.assertFalse(entry.granted)
        self.assertEqual(entry.status_code, 403)

    def test_one_shop_probing_another_is_logged(self):
        """Not only Blendy staff — any crossing at all."""
        self._get(self.outsider)

        entry = PlatformAccessLog.objects.get()
        self.assertEqual(entry.actor, self.outsider)
        self.assertFalse(entry.granted)

    def test_the_superadmin_flag_does_not_avoid_the_log(self):
        """Break-glass is still recorded, or it is a way to look unobserved."""
        self._get(self.root)

        entry = PlatformAccessLog.objects.get()
        self.assertEqual(entry.actor, self.root)
        self.assertTrue(entry.granted)

    def test_the_record_survives_the_actor_being_deleted(self):
        """A foreign key alone stops answering 'who looked at my data?'."""
        self._get(self.agent)
        self.agent.delete()

        entry = PlatformAccessLog.objects.get()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_email, "agent@blendy.test")
        self.assertEqual(entry.organization_slug, "mama-duka")


class AccessLogEndpointTests(CrossTenantBase):
    URL = "/api/organization/platform-access-log/"

    def test_a_platform_admin_can_read_the_log(self):
        self._get(self.agent)
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["actor_email"], "agent@blendy.test")

    def test_a_support_agent_cannot_read_the_log(self):
        """Reading who watched whom is an administrator's business."""
        self.client.force_authenticate(user=self.agent)

        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_a_shop_owner_cannot_read_the_log(self):
        """ORG_ADMIN holds all 87 tenant permissions and still not this one."""
        self.client.force_authenticate(user=self.owner)

        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_the_log_cannot_be_written_through_the_api(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.post(
            self.URL, {"actor_email": "forged@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 405)

    def test_a_log_entry_cannot_be_deleted_or_edited(self):
        self._get(self.agent)
        entry = PlatformAccessLog.objects.get()
        self.client.force_authenticate(user=self.platform_admin)

        for method in (self.client.delete, self.client.patch):
            with self.subTest(method=method.__name__):
                response = method(f"{self.URL}{entry.id}/")
                self.assertEqual(response.status_code, 405)
