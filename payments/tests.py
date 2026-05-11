import hashlib
import hmac
import json
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from payments.models import Payment
from payments.services.providers.factory import get_provider
from sales.models import Sale


class PaymentGatewayPhase2Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.sale = Sale.objects.create(
            customer_name="John Doe",
            customer_phone="254700000000",
            customer_email="john@example.com",
            shipping_fee=Decimal("0.00"),
        )

    def test_provider_factory_returns_mpesa_adapter(self):
        provider = get_provider(Payment.ProviderChoices.MPESA)
        charge = provider.create_charge(
            amount=Decimal("500.00"),
            currency="KES",
            phone_number="254700000000",
            idempotency_key="idem-123",
        )
        self.assertEqual(charge.status, "PENDING")
        self.assertTrue(charge.reference.startswith("mpesa_stub_"))

    @override_settings(PAYMENTS_MPESA_WEBHOOK_SECRET="secret")
    def test_mpesa_webhook_updates_payment_status(self):
        payment = Payment.objects.create(
            sale=self.sale,
            provider="MPESA",
            amount=Decimal("1000.00"),
            provider_reference="ref-1",
            status=Payment.StatusChoices.PENDING,
        )
        payload = {"provider_reference": "ref-1", "ResultCode": 0, "ResultDesc": "Success"}
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            "/api/payments/webhooks/mpesa/",
            data=payload,
            format="json",
            HTTP_X_MPESA_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.sale.refresh_from_db()
        self.assertEqual(payment.status, Payment.StatusChoices.SUCCEEDED)
        self.assertEqual(self.sale.payment_status, "PAID")
