import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payments.models import Payment
from payments.serializers import PaymentSerializer
from payments.services.providers.factory import get_provider
from payments.services.providers.mpesa import MpesaPaymentProvider
from products.models import Product, ProductVariation
from sales.models import Sale, SaleItem
from organization.models import Organization
from blendy_backend.testing import make_organization, make_priced_variation


class PaymentGatewayPhase2Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        organization = make_organization("Org 1", "org-1")
        self.sale = Sale.objects.create(
            organization=organization,
            customer_name="John Doe",
            customer_phone="254700000000",
            customer_email="john@example.com",
            shipping_fee=Decimal("0.00"),
        )

        variation = make_priced_variation(organization, "Shirt", Decimal("500.00"))
        SaleItem.objects.create(
            sale=self.sale,
            organization=organization,
            product_variation=variation,
            quantity=2,
            unit_price=Decimal("500.00"),
            discount=Decimal("0.00"),
            selling_price=Decimal("500.00"),
            total_price=Decimal("1000.00"),
        )

    @patch("payments.services.providers.mpesa.urlopen")
    @patch.object(MpesaPaymentProvider, "_get_access_token", return_value="token")
    @override_settings(
        MPESA_SHORTCODE="174379",
        MPESA_PASSKEY="passkey",
        MPESA_BASE_URL="https://sandbox.safaricom.co.ke",
        MPESA_CALLBACK_URL="https://example.com/api/payments/webhooks/mpesa/",
    )
    def test_provider_factory_returns_mpesa_adapter(self, _mock_token, mock_urlopen):
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(
            {"CheckoutRequestID": "ws_CO_123", "MerchantRequestID": "mr-123"}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        provider = get_provider(Payment.ProviderChoices.MPESA)
        charge = provider.create_charge(
            amount=Decimal("500.00"),
            currency="KES",
            phone_number="254700000000",
            idempotency_key="idem-123",
        )
        self.assertEqual(charge.status, "PENDING")
        self.assertEqual(charge.provider_reference, "ws_CO_123")
        self.assertEqual(charge.merchant_reference, "mr-123")

    def _make_payment(self, amount=Decimal("1000.00")):
        return Payment.objects.create(
            organization=self.sale.organization,
            sale=self.sale,
            provider="MPESA",
            amount=amount,
            provider_reference="ref-1",
            merchant_reference="mr-1",
            phone_number="+254700000000",
            status=Payment.StatusChoices.PENDING,
        )

    def _callback_payload(self, amount=1000.00, result_code=0):
        callback = {
            "MerchantRequestID": "mr-1",
            "CheckoutRequestID": "ref-1",
            "ResultCode": result_code,
            "ResultDesc": "The service request is processed successfully.",
        }
        if result_code == 0:
            callback["CallbackMetadata"] = {
                "Item": [
                    {"Name": "Amount", "Value": amount},
                    {"Name": "MpesaReceiptNumber", "Value": "QK12AB34CD"},
                    {"Name": "PhoneNumber", "Value": 254700000000},
                ]
            }
        return {"Body": {"stkCallback": callback}}

    @override_settings(
        MPESA_WEBHOOK_TOKEN="tok-123", MPESA_WEBHOOK_ENFORCE_IP=False
    )
    def test_mpesa_webhook_rejects_a_bad_token(self):
        payment = self._make_payment()

        response = self.client.post(
            "/api/payments/webhooks/mpesa/wrong-token/",
            data=self._callback_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.StatusChoices.PENDING)

    @override_settings(MPESA_WEBHOOK_TOKEN="", MPESA_WEBHOOK_ENFORCE_IP=False)
    def test_mpesa_webhook_fails_closed_when_token_unconfigured(self):
        self._make_payment()

        response = self.client.post(
            "/api/payments/webhooks/mpesa/anything/",
            data=self._callback_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(
        MPESA_WEBHOOK_TOKEN="tok-123",
        MPESA_WEBHOOK_ENFORCE_IP=True,
        MPESA_WEBHOOK_IP_ALLOWLIST=["196.201.214.200"],
    )
    def test_mpesa_webhook_rejects_a_non_allowlisted_ip(self):
        self._make_payment()

        response = self.client.post(
            "/api/payments/webhooks/mpesa/tok-123/",
            data=self._callback_payload(),
            format="json",
            REMOTE_ADDR="203.0.113.9",
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(
        MPESA_WEBHOOK_TOKEN="tok-123", MPESA_WEBHOOK_ENFORCE_IP=False
    )
    def test_mpesa_webhook_rejects_amount_mismatch(self):
        """A success callback for the wrong amount must not mark the sale paid."""
        payment = self._make_payment(amount=Decimal("1000.00"))

        response = self.client.post(
            "/api/payments/webhooks/mpesa/tok-123/",
            data=self._callback_payload(amount=10.00),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertNotEqual(payment.status, Payment.StatusChoices.SUCCEEDED)
        self.assertEqual(
            payment.reconciliation_status, Payment.ReconciliationStatus.MISMATCH
        )
        self.assertEqual(self.sale.payment_status, "UNPAID")

    @override_settings(
        MPESA_WEBHOOK_TOKEN="tok-123", MPESA_WEBHOOK_ENFORCE_IP=False
    )
    def test_mpesa_webhook_handles_malformed_payload_without_500(self):
        self._make_payment()

        response = self.client.post(
            "/api/payments/webhooks/mpesa/tok-123/",
            data={"unexpected": "shape"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    @override_settings(
        MPESA_WEBHOOK_TOKEN="tok-123", MPESA_WEBHOOK_ENFORCE_IP=False
    )
    def test_mpesa_webhook_updates_payment_status(self):
        payment = Payment.objects.create(
            organization=self.sale.organization,
            sale=self.sale,
            provider="MPESA",
            amount=Decimal("1000.00"),
            provider_reference="ref-1",
            merchant_reference="mr-1",
            phone_number="+254700000000",
            status=Payment.StatusChoices.PENDING,
        )
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "mr-1",
                    "CheckoutRequestID": "ref-1",
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1000.00},
                            {"Name": "MpesaReceiptNumber", "Value": "QK12AB34CD"},
                            {"Name": "PhoneNumber", "Value": 254700000000},
                        ]
                    },
                }
            }
        }

        response = self.client.post(
            "/api/payments/webhooks/mpesa/tok-123/",
            data=payload,
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(payment.status, Payment.StatusChoices.SUCCEEDED)
        self.assertEqual(self.sale.payment_status, "PAID")


class PaymentPhoneValidationTests(TestCase):
    def setUp(self):
        organization = make_organization("Org 2", "org-2")
        self.sale = Sale.objects.create(
            organization=organization,
            customer_phone="0700123456",
            shipping_fee=Decimal("0.00"),
        )
        variation = make_priced_variation(organization, "Sneaker", Decimal("1000.00"))
        SaleItem.objects.create(
            sale=self.sale,
            organization=organization,
            product_variation=variation,
            quantity=1,
            unit_price=Decimal("1000.00"),
            discount=Decimal("0.00"),
            selling_price=Decimal("1000.00"),
            total_price=Decimal("1000.00"),
        )

    def test_normalizes_kenyan_phone_to_plus_254(self):
        serializer = PaymentSerializer(data={
            "sale": str(self.sale.id),
            "provider": Payment.ProviderChoices.MANUAL,
            "amount": "1000.00",
            "phone_number": "0700 123 456",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone_number"], "+254700123456")

    def test_rejects_non_safaricom_phone_for_mpesa(self):
        serializer = PaymentSerializer(data={
            "sale": str(self.sale.id),
            "provider": Payment.ProviderChoices.MPESA,
            "amount": "1000.00",
            "phone_number": "0730123456",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("M-Pesa payments require a Safaricom phone number.", str(serializer.errors))
