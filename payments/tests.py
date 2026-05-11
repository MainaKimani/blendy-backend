from decimal import Decimal
from django.test import TestCase
from organization.models import Organization
from users.models import CustomUser
from sales.models import Sale
from payments.models import Payment
from payments.serializers import PaymentStatusUpdateSerializer, RefundSerializer


class PaymentsSerializerTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme", slug="acme")
        self.user = CustomUser.objects.create_user(
            email="agent@example.com",
            username="agent",
            password="pass1234",
            organization=self.organization,
        )
        self.sale = Sale.objects.create(customer_name="Jane Doe", created_by=self.user)
        self.payment = Payment.objects.create(
            organization=self.organization,
            sale=self.sale,
            amount=Decimal("100.00"),
            currency="KES",
            created_by=self.user,
            updated_by=self.user,
        )

    def test_payment_status_update_marks_sale_paid(self):
        serializer = PaymentStatusUpdateSerializer(
            data={"status": Payment.StatusChoices.SUCCEEDED, "provider_reference": "abc123"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        serializer.update_payment(self.payment)
        self.payment.refresh_from_db()
        self.sale.refresh_from_db()

        self.assertEqual(self.payment.status, Payment.StatusChoices.SUCCEEDED)
        self.assertEqual(self.payment.provider_reference, "abc123")
        self.assertIsNotNone(self.payment.paid_at)
        self.assertEqual(self.sale.payment_status, "PAID")

    def test_refund_serializer_rejects_invalid_amount(self):
        serializer = RefundSerializer(
            data={
                "payment": str(self.payment.id),
                "amount": "150.00",
                "reason": "Duplicate charge",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)
