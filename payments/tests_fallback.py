"""Tests for the M-Pesa fallback path: MVP §8, US-9b / US-9c / US-10."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from blendy_backend.testing import grant_role, make_organization, make_priced_variation
from organization.models import Organization
from payments.models import MpesaTransaction, Payment
from products.models import Product, ProductVariation
from sales.models import Sale, SaleItem
from users.models import CustomUser

C2B_URL = "/api/payments/webhooks/mpesa-c2b/tok-123/"

WEBHOOK_SETTINGS = dict(
    MPESA_WEBHOOK_TOKEN="tok-123",
    MPESA_WEBHOOK_ENFORCE_IP=False,
    MPESA_DIRECT_MATCH_WINDOW_HOURS=24,
    MPESA_DIRECT_MATCH_TOLERANCE="0.00",
)


class FallbackTestData:
    def make_org(self, slug, shortcode=None):
        return make_organization(slug, slug, mpesa_shortcode=shortcode)

    def make_sale(self, organization, phone, total, payment_status, created_at=None):
        variation = make_priced_variation(
            organization, f"Item {total}", total
        )
        sale = Sale.objects.create(
            organization=organization,
            customer_phone=phone,
            payment_status=payment_status,
        )
        SaleItem.objects.create(
            sale=sale,
            organization=organization,
            product_variation=variation,
            quantity=1,
            unit_price=total,
            selling_price=total,
            total_price=total,
        )
        if created_at is not None:
            # auto_now_add ignores assignment, so write it directly.
            Sale.objects.filter(pk=sale.pk).update(created_at=created_at)
            sale.refresh_from_db()
        return sale

    def c2b_payload(self, phone="254700123456", amount="1000.00", trans_id="RKT1"):
        return {
            "TransactionType": "Pay Bill",
            "TransID": trans_id,
            "TransTime": "20260814063845",
            "TransAmount": amount,
            "BusinessShortCode": "174379",
            "BillRefNumber": "",
            "MSISDN": phone,
            "FirstName": "John",
        }


@override_settings(**WEBHOOK_SETTINGS)
class DirectPaymentMatchingTests(APITestCase, FallbackTestData):
    def setUp(self):
        self.org = self.make_org("shop-a", shortcode="174379")

    def test_matching_direct_payment_reconciles_the_open_sale(self):
        sale = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        response = self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["matched"])

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "PAID")

        payment = Payment.objects.get(sale=sale)
        self.assertEqual(payment.status, Payment.StatusChoices.SUCCEEDED)
        self.assertEqual(
            payment.reconciliation_status, Payment.ReconciliationStatus.MATCHED
        )
        self.assertEqual(payment.provider_reference, "RKT1")

        txn = MpesaTransaction.objects.get(mpesa_receipt_number="RKT1")
        self.assertEqual(txn.payment_id, payment.id)
        self.assertIsNotNone(txn.transaction_date)

    def test_phone_formats_are_normalised_before_matching(self):
        """The sale stores 07…; M-Pesa sends 2547…. They must still match."""
        sale = self.make_sale(
            self.org, "0700 123 456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        self.client.post(C2B_URL, self.c2b_payload(), format="json")

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "PAID")

    def test_unmatched_payment_is_kept_not_dropped(self):
        self.make_sale(
            self.org, "0700999999", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        response = self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["matched"])

        txn = MpesaTransaction.objects.get(mpesa_receipt_number="RKT1")
        self.assertIsNone(txn.payment_id)
        self.assertIn("No open sale", txn.reconciliation_note)

    def test_amount_mismatch_does_not_reconcile(self):
        sale = self.make_sale(
            self.org, "0700123456", Decimal("1500.00"), "AWAITING_DIRECT_PAYMENT"
        )

        self.client.post(C2B_URL, self.c2b_payload(amount="1000.00"), format="json")

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "AWAITING_DIRECT_PAYMENT")
        self.assertIsNone(
            MpesaTransaction.objects.get(mpesa_receipt_number="RKT1").payment_id
        )

    def test_ambiguous_match_is_refused_and_explained(self):
        first = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )
        second = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        response = self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertFalse(response.data["matched"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.payment_status, "AWAITING_DIRECT_PAYMENT")
        self.assertEqual(second.payment_status, "AWAITING_DIRECT_PAYMENT")

        note = MpesaTransaction.objects.get(mpesa_receipt_number="RKT1").reconciliation_note
        self.assertIn("Ambiguous", note)
        self.assertIn(str(first.id), note)
        self.assertIn(str(second.id), note)

    def test_sale_outside_the_match_window_is_not_matched(self):
        sale = self.make_sale(
            self.org,
            "0700123456",
            Decimal("1000.00"),
            "AWAITING_DIRECT_PAYMENT",
            created_at=timezone.now() - timedelta(hours=30),
        )

        self.client.post(C2B_URL, self.c2b_payload(), format="json")

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "AWAITING_DIRECT_PAYMENT")

    def test_sale_not_awaiting_direct_payment_is_not_matched(self):
        """An already-paid sale must not absorb an unrelated incoming payment."""
        sale = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "PAID"
        )

        self.client.post(C2B_URL, self.c2b_payload(), format="json")

        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "PAID")
        self.assertEqual(Payment.objects.count(), 0)

    def test_repeated_confirmation_does_not_double_credit(self):
        sale = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        self.client.post(C2B_URL, self.c2b_payload(), format="json")
        self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertEqual(MpesaTransaction.objects.count(), 1)
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 1)

    def test_bad_token_is_rejected(self):
        self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        response = self.client.post(
            "/api/payments/webhooks/mpesa-c2b/wrong/",
            self.c2b_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(MpesaTransaction.objects.count(), 0)


@override_settings(**WEBHOOK_SETTINGS)
class DirectPaymentTenantScopingTests(APITestCase, FallbackTestData):
    def test_payment_only_matches_sales_of_the_owning_tenant(self):
        org_a = self.make_org("shop-a", shortcode="174379")
        org_b = self.make_org("shop-b", shortcode="999999")

        sale_b = self.make_sale(
            org_b, "0700123456", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )

        # Paid into org A's till; org B's identical sale must not be touched.
        response = self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertFalse(response.data["matched"])
        sale_b.refresh_from_db()
        self.assertEqual(sale_b.payment_status, "AWAITING_DIRECT_PAYMENT")
        self.assertEqual(
            MpesaTransaction.objects.get(mpesa_receipt_number="RKT1").organization_id,
            org_a.id,
        )

    def test_unknown_shortcode_is_acknowledged_but_not_recorded(self):
        self.make_org("shop-a", shortcode="111111")

        response = self.client.post(
            C2B_URL, self.c2b_payload(), format="json"
        )

        # Acknowledged so Safaricom stops retrying, but nothing is attributed.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MpesaTransaction.objects.count(), 0)


@override_settings(**WEBHOOK_SETTINGS)
class StkFailureKeepsSaleOpenTests(APITestCase, FallbackTestData):
    """US-9b: a failed push must not kill the sale."""

    def setUp(self):
        self.org = self.make_org("shop-a", shortcode="174379")
        self.sale = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "UNPAID"
        )
        self.payment = Payment.objects.create(
            organization=self.org,
            sale=self.sale,
            provider="MPESA",
            amount=Decimal("1000.00"),
            provider_reference="ref-1",
            merchant_reference="mr-1",
            phone_number="+254700123456",
            status=Payment.StatusChoices.PENDING,
        )

    def test_failed_stk_push_moves_sale_to_awaiting_direct_payment(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "mr-1",
                    "CheckoutRequestID": "ref-1",
                    "ResultCode": 1032,
                    "ResultDesc": "Request cancelled by user",
                }
            }
        }

        response = self.client.post(
            "/api/payments/webhooks/mpesa/tok-123/", payload, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.sale.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.StatusChoices.FAILED)
        self.assertEqual(self.sale.payment_status, "AWAITING_DIRECT_PAYMENT")

    def test_exhausted_retries_cancel_the_payment_not_the_sale(self):
        self.payment.status = Payment.StatusChoices.FAILED
        self.payment.retry_count = self.payment.max_retries
        self.payment.next_retry_at = timezone.now() - timedelta(minutes=1)
        self.payment.save()

        call_command("reconcile_payments")

        self.payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.StatusChoices.CANCELLED)
        self.assertEqual(self.sale.payment_status, "AWAITING_DIRECT_PAYMENT")

    def test_a_direct_payment_can_still_settle_the_sale_afterwards(self):
        """End to end: push fails, retries exhaust, customer pays the Till."""
        self.payment.status = Payment.StatusChoices.FAILED
        self.payment.retry_count = self.payment.max_retries
        self.payment.next_retry_at = timezone.now() - timedelta(minutes=1)
        self.payment.save()
        call_command("reconcile_payments")

        response = self.client.post(C2B_URL, self.c2b_payload(), format="json")

        self.assertTrue(response.data["matched"])
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.payment_status, "PAID")


@override_settings(**WEBHOOK_SETTINGS)
class PendingPaymentQueueTests(APITestCase, FallbackTestData):
    """US-10: nothing unmatched is silently dropped."""

    def setUp(self):
        self.org = self.make_org("shop-a", shortcode="174379")
        self.other = self.make_org("shop-b", shortcode="999999")
        self.user = CustomUser.objects.create_user(
            email="o@shop.test", username="o", password="pw", organization=self.org
        )
        grant_role(self.user, self.org)
        self.sale = self.make_sale(
            self.org, "0700999999", Decimal("1000.00"), "AWAITING_DIRECT_PAYMENT"
        )
        # An inbound payment that matches nothing.
        self.client.post(C2B_URL, self.c2b_payload(), format="json")

    def test_unmatched_transactions_are_listed_for_the_tenant(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            "/api/payments/payments/unmatched/",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(
            response.data["results"][0]["mpesa_receipt_number"], "RKT1"
        )

    def test_unmatched_list_requires_authentication(self):
        response = self.client.get("/api/payments/payments/unmatched/")

        self.assertIn(response.status_code, (401, 403))

    def test_sales_awaiting_payment_are_listed(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            "/api/sales/sales/pending-payments/",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_items"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.sale.id))


class AnonymousStkPushThrottleTests(APITestCase, FallbackTestData):
    """Guest checkout stays open, but cannot be used to spam STK prompts."""

    def setUp(self):
        cache.clear()
        self.org = make_organization("Shop", "shop")
        self.sale = self.make_sale(
            self.org, "0700123456", Decimal("1000.00"), "UNPAID"
        )

    def tearDown(self):
        cache.clear()

    def _post_payment(self, phone="0700123456"):
        return self.client.post(
            "/api/payments/payments/",
            {
                "sale": str(self.sale.id),
                "provider": Payment.ProviderChoices.MANUAL,
                "amount": "1000.00",
                "phone_number": phone,
            },
            format="json",
            HTTP_X_ORGANIZATION=str(self.org.id),
        )

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": (
                "rest_framework_simplejwt.authentication.JWTAuthentication",
            ),
            "DEFAULT_PAGINATION_CLASS": (
                "blendy_backend.pagination.StandardResultsSetPagination"
            ),
            "PAGE_SIZE": 20,
            "DEFAULT_THROTTLE_RATES": {
                "stk_push_phone": "2/hour",
                "stk_push_ip": "100/hour",
            },
        }
    )
    def test_anonymous_creates_are_throttled_per_phone_number(self):
        self.assertEqual(self._post_payment().status_code, 201)
        self.assertEqual(self._post_payment().status_code, 201)

        self.assertEqual(self._post_payment().status_code, 429)

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": (
                "rest_framework_simplejwt.authentication.JWTAuthentication",
            ),
            "DEFAULT_PAGINATION_CLASS": (
                "blendy_backend.pagination.StandardResultsSetPagination"
            ),
            "PAGE_SIZE": 20,
            "DEFAULT_THROTTLE_RATES": {
                "stk_push_phone": "2/hour",
                "stk_push_ip": "100/hour",
            },
        }
    )
    def test_authenticated_staff_are_not_throttled(self):
        user = CustomUser.objects.create_user(
            email="till@shop.test", username="till", password="pw",
            organization=self.org,
        )
        grant_role(user, self.org)
        self.client.force_authenticate(user=user)

        for _ in range(4):
            self.assertEqual(self._post_payment().status_code, 201)
