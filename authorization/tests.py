"""Tenant scoping for role assignments.

UserRoleAssignment has no organization column — it is tenanted through
organization_role. The viewset inherited OrganizationBaseViewSet's scoping,
which filtered on `organization`, so every request raised FieldError and the
isolation the base was assumed to provide was never applied.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from authorization.models import OrganizationRole, Permission, Role, UserRoleAssignment
from blendy_backend.testing import make_organization
from users.models import CustomUser


class UserRoleAssignmentScopingTests(APITestCase):
    URL = "/api/authorization/user-role-assignments/"

    def setUp(self):
        self.org_a = make_organization("Shop A", "shop-a")
        self.org_b = make_organization("Shop B", "shop-b")

        self.user_a, self.assignment_a = self._staff(self.org_a, "a", "CASHIER_A")
        self.user_b, self.assignment_b = self._staff(self.org_b, "b", "CASHIER_B")

    def _staff(self, organization, handle, role_name):
        user = CustomUser.objects.create_user(
            email=f"{handle}@shop.test", username=handle, password="pw",
            organization=organization, is_organization_admin=True,
        )
        role, _ = Role.objects.get_or_create(name=role_name)
        permission, _ = Permission.objects.get_or_create(name=f"{handle}.view")
        role.permissions.add(permission)
        org_role = OrganizationRole.objects.create(
            organization=organization, role=role
        )
        assignment = UserRoleAssignment.objects.create(
            user=user, organization_role=org_role
        )
        return user, assignment

    def _get(self, user, organization, path=None):
        self.client.force_authenticate(user=user)
        return self.client.get(
            path or self.URL, HTTP_X_ORGANIZATION=str(organization.id)
        )

    def test_listing_no_longer_raises(self):
        """The regression: this used to raise FieldError before reading a row."""
        response = self._get(self.user_a, self.org_a)

        self.assertEqual(response.status_code, 200, response.data)

    def test_listing_returns_only_the_callers_tenant(self):
        response = self._get(self.user_a, self.org_a)

        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.assignment_a.id))

    def test_another_tenants_assignment_is_not_retrievable(self):
        response = self._get(
            self.user_a, self.org_a, path=f"{self.URL}{self.assignment_b.id}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_no_tenant_header_returns_nothing(self):
        """Fail closed: a missing tenant must not mean every tenant."""
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(self.URL)

        # IsOrganizationUser rejects the request outright; if it ever stopped
        # doing so, the queryset must still yield nothing.
        self.assertIn(response.status_code, (403, 200))
        if response.status_code == 200:
            self.assertEqual(response.data["total_items"], 0)

    def test_assignments_cannot_be_written_through_this_endpoint(self):
        """Roles are assigned via /api/users/; this view is a read model.

        Left writable it raised TypeError, because both of the serializer's
        relations are read-only and the create had nothing to write.
        """
        self.client.force_authenticate(user=self.user_a)

        response = self.client.post(
            self.URL,
            {
                "user": str(self.user_a.id),
                "organization_role": str(self.assignment_a.organization_role_id),
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org_a.id),
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(UserRoleAssignment.objects.count(), 2)

    def test_listing_does_not_query_per_row(self):
        role = Role.objects.create(name="EXTRA")
        org_role = OrganizationRole.objects.create(
            organization=self.org_a, role=role
        )
        for i in range(10):
            user = CustomUser.objects.create_user(
                email=f"extra{i}@shop.test", username=f"extra{i}", password="pw",
                organization=self.org_a,
            )
            UserRoleAssignment.objects.create(user=user, organization_role=org_role)

        self.client.force_authenticate(user=self.user_a)
        with CaptureQueriesContext(connection) as few:
            self.client.get(
                f"{self.URL}?page_size=1", HTTP_X_ORGANIZATION=str(self.org_a.id)
            )
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(
                self.URL, HTTP_X_ORGANIZATION=str(self.org_a.id)
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_items"], 11)
        self.assertEqual(
            len(few.captured_queries),
            len(many.captured_queries),
            f"{self.URL} issues {len(few.captured_queries)} queries for 1 row "
            f"but {len(many.captured_queries)} for 11 — an N+1.",
        )


class OrganizationRoleWriteTests(APITestCase):
    """Enabling a role for an organization.

    This is the only path that links a Role to an Organization, so unlike the
    assignment endpoint above it has to actually work. Both of the serializer's
    relations were read-only, leaving nothing writable: a create wrote no role
    and failed on the not-null column.
    """

    URL = "/api/authorization/organization-roles/"

    def setUp(self):
        self.org = make_organization("Shop A", "shop-a")
        self.other = make_organization("Shop B", "shop-b")
        self.admin = CustomUser.objects.create_user(
            email="admin@shop.test", username="admin", password="pw",
            organization=self.org, is_organization_admin=True,
        )
        self.role = Role.objects.create(name="STOCK_CLERK")
        permission, _ = Permission.objects.get_or_create(name="sales.add_sale")
        self.role.permissions.add(permission)
        self.client.force_authenticate(user=self.admin)

    def _post(self, role, organization=None):
        return self.client.post(
            self.URL,
            {"role_id": str(role.id)},
            format="json",
            HTTP_X_ORGANIZATION=str((organization or self.org).id),
        )

    def test_a_role_can_be_enabled_for_the_organization(self):
        response = self._post(self.role)

        self.assertEqual(response.status_code, 201, response.data)
        org_role = OrganizationRole.objects.get(id=response.data["id"])
        self.assertEqual(org_role.role, self.role)
        self.assertEqual(org_role.organization, self.org)

    def test_the_tenant_comes_from_the_header_not_the_body(self):
        """A caller must not be able to enable a role for someone else's shop."""
        response = self.client.post(
            self.URL,
            {"role_id": str(self.role.id), "organization": str(self.other.id)},
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 201, response.data)
        org_role = OrganizationRole.objects.get(id=response.data["id"])
        self.assertEqual(org_role.organization, self.org)
        self.assertFalse(
            OrganizationRole.objects.filter(
                organization=self.other, role=self.role
            ).exists()
        )

    def test_enabling_the_same_role_twice_is_rejected_not_a_500(self):
        self.assertEqual(self._post(self.role).status_code, 201)

        response = self._post(self.role)

        self.assertEqual(response.status_code, 400)
        self.assertIn("already enabled", str(response.data))
        self.assertEqual(
            OrganizationRole.objects.filter(
                organization=self.org, role=self.role
            ).count(),
            1,
        )

    def test_a_missing_role_is_rejected(self):
        response = self.client.post(
            self.URL, {}, format="json", HTTP_X_ORGANIZATION=str(self.org.id)
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("role_id", response.data)

    def test_the_response_nests_the_role_it_enabled(self):
        response = self._post(self.role)

        self.assertEqual(response.data["role"]["name"], "STOCK_CLERK")
        self.assertEqual(response.data["organization"]["slug"], "shop-a")

    def test_listing_returns_only_the_callers_tenant(self):
        self._post(self.role)
        other_role = Role.objects.create(name="OTHER")
        OrganizationRole.objects.create(organization=self.other, role=other_role)

        response = self.client.get(self.URL, HTTP_X_ORGANIZATION=str(self.org.id))

        self.assertEqual(response.status_code, 200, response.data)
        names = {row["role"]["name"] for row in response.data["results"]}
        # The built-in roles are enabled for every shop, so what matters is that
        # this shop's own role is present and the other shop's is not.
        self.assertIn("STOCK_CLERK", names)
        self.assertNotIn("OTHER", names)

    def test_listing_does_not_query_per_row(self):
        for i in range(10):
            OrganizationRole.objects.create(
                organization=self.org, role=Role.objects.create(name=f"ROLE-{i}")
            )

        with CaptureQueriesContext(connection) as few:
            self.client.get(
                f"{self.URL}?page_size=1", HTTP_X_ORGANIZATION=str(self.org.id)
            )
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(self.URL, HTTP_X_ORGANIZATION=str(self.org.id))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["total_items"],
            OrganizationRole.objects.filter(organization=self.org).count(),
        )
        self.assertEqual(
            len(few.captured_queries),
            len(many.captured_queries),
            f"{self.URL} issues {len(few.captured_queries)} queries for 1 row "
            f"but {len(many.captured_queries)} for the full page — an N+1.",
        )

    def test_an_enabled_role_can_then_be_assigned_to_a_user(self):
        """The point of the endpoint: it feeds the assignment flow on /api/users/."""
        org_role_id = self._post(self.role).data["id"]
        cashier = CustomUser.objects.create_user(
            email="cashier@shop.test", username="cashier", password="pw",
            organization=self.org,
        )

        response = self.client.patch(
            f"/api/users/{cashier.id}/",
            {"organization_role_ids": [org_role_id]},
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 200, response.data)
        cashier.refresh_from_db()
        self.assertIn("sales.add_sale", cashier.get_permission_names())
