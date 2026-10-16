"""GET /api/users/me/ — the caller's identity and effective access."""

from rest_framework.test import APITestCase

from authorization.rbac import CASHIER, ORG_ADMIN
from blendy_backend.testing import make_organization, make_user
from users.models import CustomUser

URL = "/api/users/me/"


class MeViewTests(APITestCase):
    def setUp(self):
        self.shop = make_organization(name="Mama Duka", slug="mama-duka")
        self.other = make_organization(name="Other", slug="other")

    def test_anonymous_callers_are_refused(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_a_cashier_sees_their_own_roles_and_permissions(self):
        cashier = make_user(self.shop, role=CASHIER)
        self.client.force_authenticate(cashier)

        response = self.client.get(URL)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["roles"], [CASHIER])
        self.assertIn("sales.add_sale", body["permissions"])
        self.assertNotIn("inventory.restock_stock", body["permissions"])
        self.assertEqual(body["organization"]["id"], str(self.shop.id))
        self.assertFalse(body["organization"]["is_platform"])
        self.assertFalse(body["is_superuser_admin"])

    def test_the_owner_holds_restock(self):
        owner = make_user(self.shop, role=ORG_ADMIN)
        self.client.force_authenticate(owner)

        body = self.client.get(URL).json()

        self.assertEqual(body["roles"], [ORG_ADMIN])
        self.assertIn("inventory.restock_stock", body["permissions"])

    def test_the_header_does_not_change_whose_access_is_reported(self):
        # Access is always the caller's own; naming another shop must neither
        # widen it nor be refused, since the client calls this before choosing.
        cashier = make_user(self.shop, role=CASHIER)
        self.client.force_authenticate(cashier)

        body = self.client.get(
            URL, HTTP_X_ORGANIZATION=str(self.other.id)
        ).json()

        self.assertEqual(body["organization"]["id"], str(self.shop.id))
        self.assertEqual(body["roles"], [CASHIER])

    def test_a_superadmin_is_flagged(self):
        admin = CustomUser.objects.create_user(
            email="root@blendy.test", username="root", password="pw",
            is_superuser_admin=True,
        )
        self.client.force_authenticate(admin)

        body = self.client.get(URL).json()

        self.assertTrue(body["is_superuser_admin"])
        self.assertIsNone(body["organization"])
        self.assertEqual(body["permissions"], [])
