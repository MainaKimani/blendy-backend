"""Managing Blendy's own staff, and onboarding without the flag.

The point of T7 is that day-to-day platform work stops requiring
`is_superuser_admin`. The flag stays as break-glass; everything routine goes
through a permission that can be granted and revoked per person.
"""

from authorization.models import OrganizationRole, UserRoleAssignment
from authorization.rbac import (
    CASHIER,
    ORG_ADMIN,
    PLATFORM_ADMIN,
    SUPPORT_AGENT,
)
from blendy_backend.testing import make_organization
from organization.models import Organization
from organization.services import get_platform_organization
from rest_framework.test import APITestCase
from users.models import CustomUser


class PlatformStaffBase(APITestCase):
    def setUp(self):
        self.hq = get_platform_organization()
        self.shop = make_organization("Mama Duka", "mama-duka")
        self.other_shop = make_organization("Duka Mbili", "duka-mbili")

        self.hq_headers = {"HTTP_X_ORGANIZATION": str(self.hq.id)}
        self.shop_headers = {"HTTP_X_ORGANIZATION": str(self.shop.id)}

        self.platform_admin = self._user("admin@blendy.test", self.hq, PLATFORM_ADMIN)
        self.agent = self._user("agent@blendy.test", self.hq, SUPPORT_AGENT)
        self.owner = self._user(
            "owner@mama-duka.test", self.shop, ORG_ADMIN, is_organization_admin=True
        )
        self.other_owner = self._user(
            "owner@duka-mbili.test", self.other_shop, ORG_ADMIN,
            is_organization_admin=True,
        )
        self.cashier = self._user("till@mama-duka.test", self.shop, CASHIER)
        self.root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )

    def _user(self, email, organization, role_name, **kwargs):
        user = CustomUser.objects.create_user(
            email=email, username=email, password="pw",
            organization=organization, **kwargs
        )
        UserRoleAssignment.objects.create(
            user=user,
            organization_role=OrganizationRole.objects.get(
                organization=organization, role__name=role_name
            ),
        )
        return user


class OnboardingWithoutTheFlagTests(PlatformStaffBase):
    URL = "/api/organization/onboard/"

    def _onboard(self, slug="new-shop"):
        return self.client.post(
            self.URL,
            {
                "organization": {"name": slug.title(), "slug": slug},
                "user": {
                    "email": f"owner@{slug}.test",
                    "username": f"owner@{slug}.test",
                    "password": "pw",
                },
            },
            format="json",
        )

    def test_a_platform_admin_can_onboard_a_shop(self):
        """The point of T7: this used to require the superadmin flag."""
        self.client.force_authenticate(user=self.platform_admin)

        response = self._onboard()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Organization.objects.filter(slug="new-shop").exists())

    def test_the_superadmin_flag_still_onboards(self):
        """Break-glass is retained, not replaced."""
        self.client.force_authenticate(user=self.root)

        self.assertEqual(self._onboard("root-shop").status_code, 201)

    def test_a_support_agent_cannot_onboard(self):
        """Support reads; it does not create customers."""
        self.client.force_authenticate(user=self.agent)

        self.assertEqual(self._onboard().status_code, 403)

    def test_a_shop_owner_cannot_onboard(self):
        self.client.force_authenticate(user=self.owner)

        self.assertEqual(self._onboard().status_code, 403)

    def test_an_onboarded_shop_is_not_a_platform_organization(self):
        self.client.force_authenticate(user=self.platform_admin)

        self._onboard()

        self.assertFalse(Organization.objects.get(slug="new-shop").is_platform)
        self.assertEqual(Organization.objects.filter(is_platform=True).count(), 1)


class HQStaffManagementTests(PlatformStaffBase):
    URL = "/api/users/"

    def test_a_platform_admin_can_create_hq_staff(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.post(
            self.URL,
            {"email": "new@blendy.test", "username": "new@blendy.test",
             "password": "pw"},
            format="json",
            **self.hq_headers,
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            CustomUser.objects.get(email="new@blendy.test").organization, self.hq
        )

    def test_new_hq_staff_can_be_given_a_platform_role(self):
        """The whole loop: hire someone into HQ and give them support access."""
        self.client.force_authenticate(user=self.platform_admin)
        support_role = OrganizationRole.objects.get(
            organization=self.hq, role__name=SUPPORT_AGENT
        )

        response = self.client.post(
            self.URL,
            {
                "email": "new@blendy.test", "username": "new@blendy.test",
                "password": "pw",
                "organization_role_ids": [str(support_role.id)],
            },
            format="json",
            **self.hq_headers,
        )

        self.assertEqual(response.status_code, 201, response.data)
        hire = CustomUser.objects.get(email="new@blendy.test")
        self.assertIn("platform.access_tenants", hire.get_permission_names())

    def test_a_support_agent_cannot_hire(self):
        self.client.force_authenticate(user=self.agent)

        response = self.client.post(
            self.URL,
            {"email": "x@blendy.test", "username": "x@blendy.test", "password": "pw"},
            format="json",
            **self.hq_headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_a_shop_owner_cannot_reach_hq_staff(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(self.URL, **self.hq_headers)

        self.assertEqual(response.status_code, 403)

    def test_a_platform_admin_can_manage_a_shops_staff_while_acting_as_it(self):
        self.client.force_authenticate(user=self.platform_admin)

        response = self.client.get(self.URL, **self.shop_headers)

        self.assertEqual(response.status_code, 200, response.data)
        emails = {row["email"] for row in response.data["results"]}
        self.assertIn("owner@mama-duka.test", emails)
        self.assertNotIn("owner@duka-mbili.test", emails)


class OneShopCannotAdministerAnotherTests(PlatformStaffBase):
    """A pre-existing cross-tenant hole, closed by T7.

    CustomUserViewSet applied IsOrganizationUser only to update. The queryset
    and perform_create both read the organization from the X-Organization
    header, so the admin of one shop could list and create users inside another
    just by changing it.
    """

    URL = "/api/users/"

    def test_an_owner_cannot_create_a_user_inside_another_shop(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            self.URL,
            {"email": "planted@shop.test", "username": "planted@shop.test",
             "password": "pw"},
            format="json",
            HTTP_X_ORGANIZATION=str(self.other_shop.id),
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            CustomUser.objects.filter(email="planted@shop.test").exists()
        )

    def test_an_owner_cannot_list_another_shops_users(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            self.URL, HTTP_X_ORGANIZATION=str(self.other_shop.id)
        )

        self.assertEqual(response.status_code, 403)

    def test_an_owner_can_still_manage_their_own_staff(self):
        """The fix must not cost a shop its own user management."""
        self.client.force_authenticate(user=self.owner)

        listing = self.client.get(self.URL, **self.shop_headers)
        created = self.client.post(
            self.URL,
            {"email": "new@mama-duka.test", "username": "new@mama-duka.test",
             "password": "pw"},
            format="json",
            **self.shop_headers,
        )

        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(created.status_code, 201, created.data)

    def test_a_cashier_cannot_manage_staff_at_all(self):
        self.client.force_authenticate(user=self.cashier)

        self.assertEqual(
            self.client.get(self.URL, **self.shop_headers).status_code, 403
        )

    def test_the_attempt_is_recorded(self):
        """A cross-tenant probe leaves a trail even when refused."""
        from organization.models import PlatformAccessLog

        self.client.force_authenticate(user=self.owner)
        self.client.get(self.URL, HTTP_X_ORGANIZATION=str(self.other_shop.id))

        entry = PlatformAccessLog.objects.get()
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.organization_slug, "duka-mbili")
        self.assertFalse(entry.granted)
