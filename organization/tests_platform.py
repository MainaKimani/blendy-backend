"""The HQ organization: it exists, it is unique, and it is not a customer.

HQ is an Organization so that platform staff can use the same RBAC a shop's
staff use. The cost of that choice is that every place meaning "a customer" has
to say so — these tests pin the three that did not.
"""

from decimal import Decimal

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.test import APITestCase

from authorization.models import OrganizationRole
from authorization.rbac import DEFAULT_ORGANIZATION_ROLES, enable_default_roles
from blendy_backend.testing import make_organization
from organization.models import Organization
from organization.services import (
    PlatformOrganizationMissing,
    create_platform_organization,
    get_platform_organization,
    require_platform_organization,
    tenants,
)
from pricing.models import Pricelist
from users.models import CustomUser


class PlatformOrganizationTests(APITestCase):
    def test_migration_created_exactly_one_hq(self):
        self.assertEqual(Organization.objects.filter(is_platform=True).count(), 1)

    def test_hq_is_resolvable(self):
        hq = get_platform_organization()

        self.assertIsNotNone(hq)
        self.assertTrue(hq.is_platform)
        self.assertEqual(require_platform_organization(), hq)

    def test_a_second_hq_is_refused_by_the_database(self):
        """The constraint, not a convention, is what guarantees one HQ."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(
                    name="Rogue HQ", slug="rogue-hq", is_platform=True
                )

    def test_creating_hq_twice_returns_the_existing_one(self):
        hq = get_platform_organization()

        again, created = create_platform_organization()

        self.assertEqual(again.id, hq.id)
        self.assertFalse(created)

    def test_require_raises_when_hq_is_absent(self):
        Organization.objects.filter(is_platform=True).delete()

        with self.assertRaises(PlatformOrganizationMissing):
            require_platform_organization()

    def test_hq_is_not_a_tenant(self):
        shop = make_organization("Shop", "shop")

        listed = set(tenants().values_list("slug", flat=True))

        self.assertIn(shop.slug, listed)
        self.assertNotIn(get_platform_organization().slug, listed)

    def test_hq_has_no_pricelist_and_no_shop_roles(self):
        """It never sells, so seeding it as a shop would be incoherent.

        HQ does hold the *platform* roles — those are what it is for.
        """
        hq = get_platform_organization()

        self.assertFalse(Pricelist.objects.filter(organization=hq).exists())
        enabled = set(
            OrganizationRole.objects.filter(organization=hq).values_list(
                "role__name", flat=True
            )
        )
        self.assertEqual(enabled & set(DEFAULT_ORGANIZATION_ROLES), set())

    def test_enabling_default_roles_still_skips_hq(self):
        """enable_default_roles walks every organization; HQ must not be one."""
        make_organization("Shop", "shop")

        enable_default_roles()

        hq = get_platform_organization()
        enabled = set(
            OrganizationRole.objects.filter(organization=hq).values_list(
                "role__name", flat=True
            )
        )
        self.assertEqual(enabled & set(DEFAULT_ORGANIZATION_ROLES), set())


class PlatformFlagIsNotClientSettableTests(APITestCase):
    """`fields = '__all__'` had made is_platform writable."""

    def setUp(self):
        self.root = CustomUser.objects.create_superuser(
            email="root@blendy.test", username="root", password="pw"
        )
        self.client.force_authenticate(user=self.root)

    def test_creating_an_organization_cannot_make_it_platform(self):
        response = self.client.post(
            "/api/organization/",
            {"name": "Sneaky", "slug": "sneaky", "is_platform": True},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(Organization.objects.get(slug="sneaky").is_platform)

    def test_onboarding_cannot_create_a_platform_organization(self):
        response = self.client.post(
            "/api/organization/onboard/",
            {
                "organization": {"name": "Duka", "slug": "duka", "is_platform": True},
                "user": {"email": "o@duka.test", "username": "o", "password": "pw"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(Organization.objects.get(slug="duka").is_platform)
        self.assertEqual(Organization.objects.filter(is_platform=True).count(), 1)

    def test_an_existing_organization_cannot_be_promoted_to_platform(self):
        organization = make_organization("Shop", "shop")

        response = self.client.patch(
            f"/api/organization/{organization.id}/",
            {"is_platform": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        organization.refresh_from_db()
        self.assertFalse(organization.is_platform)

    def test_hq_is_not_listed_as_a_customer(self):
        make_organization("Shop", "shop")

        response = self.client.get("/api/organization/")

        slugs = [row["slug"] for row in response.data["results"]]
        self.assertIn("shop", slugs)
        self.assertNotIn(get_platform_organization().slug, slugs)

    def test_hq_is_not_retrievable_through_the_tenant_route(self):
        hq = get_platform_organization()

        response = self.client.get(f"/api/organization/{hq.id}/")

        self.assertEqual(response.status_code, 404)


@override_settings(MPESA_SHORTCODE="174379", MPESA_WEBHOOK_TOKEN="tok-123",
                   MPESA_WEBHOOK_ENFORCE_IP=False)
class ShortcodeFallbackIgnoresHQTests(APITestCase):
    """The single-tenant C2B fallback counts customers, not organizations.

    It read `Organization.objects.all()[:2]` and returned `[0]` when there was
    exactly one. Creating HQ makes that count two, which both breaks a genuinely
    single-tenant deployment and — since the ordering is arbitrary — risks
    attributing a shop's money to us.
    """

    def test_the_sole_tenant_still_resolves_once_hq_exists(self):
        from payments.services.reconciliation import resolve_organization

        shop = make_organization("Only Shop", "only-shop")
        self.assertEqual(Organization.objects.count(), 2)  # shop + HQ

        self.assertEqual(resolve_organization("174379"), shop)

    def test_hq_is_never_returned_as_the_sole_tenant(self):
        from payments.services.reconciliation import (
            TenantNotResolved,
            resolve_organization,
        )

        # HQ alone, no customers at all.
        self.assertEqual(tenants().count(), 0)

        with self.assertRaises(TenantNotResolved):
            resolve_organization("174379")

    def test_an_explicit_shortcode_never_resolves_to_hq(self):
        from payments.services.reconciliation import (
            TenantNotResolved,
            resolve_organization,
        )

        hq = get_platform_organization()
        hq.mpesa_shortcode = "999999"
        hq.save(update_fields=["mpesa_shortcode"])

        with self.assertRaises(TenantNotResolved):
            resolve_organization("999999")


class BootstrapCommandTests(APITestCase):
    def test_the_command_is_idempotent(self):
        call_command("bootstrap_hq")

        self.assertEqual(Organization.objects.filter(is_platform=True).count(), 1)

    def test_it_can_rename_hq_without_changing_which_org_is_hq(self):
        before = get_platform_organization().id

        call_command("bootstrap_hq", name="Blendy Platform", slug="blendy-platform")

        hq = get_platform_organization()
        self.assertEqual(hq.id, before)
        self.assertEqual(hq.name, "Blendy Platform")
        self.assertEqual(hq.slug, "blendy-platform")

    def test_it_promotes_a_user_into_hq(self):
        user = CustomUser.objects.create_user(
            email="staff@blendy.test", username="staff", password="pw"
        )

        call_command("bootstrap_hq", promote="staff@blendy.test")

        user.refresh_from_db()
        self.assertEqual(user.organization, get_platform_organization())

    def test_promoting_an_unknown_user_fails_loudly(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("bootstrap_hq", promote="nobody@blendy.test")
