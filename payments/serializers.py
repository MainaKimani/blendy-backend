from django.utils import timezone
from rest_framework import serializers
from .models import Payment, Refund


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = (
            "organization",
            "status",
            "provider_reference",
            "failure_reason",
            "paid_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        sale = attrs.get("sale")
        amount = attrs.get("amount")
        if sale and amount and amount <= 0:
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return attrs


class PaymentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Payment.StatusChoices.choices)
    provider_reference = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True)

    def update_payment(self, payment):
        status_value = self.validated_data["status"]
        payment.status = status_value
        payment.provider_reference = self.validated_data.get("provider_reference", "")
        payment.failure_reason = self.validated_data.get("failure_reason", "")
        if status_value == Payment.StatusChoices.SUCCEEDED:
            payment.paid_at = timezone.now()
            payment.sale.payment_status = "PAID"
        elif status_value == Payment.StatusChoices.REFUNDED:
            payment.sale.payment_status = "REFUNDED"
        elif status_value in [Payment.StatusChoices.FAILED, Payment.StatusChoices.CANCELLED]:
            payment.sale.payment_status = "UNPAID"

        payment.sale.save(update_fields=["payment_status"])
        payment.save()
        return payment


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = "__all__"
        read_only_fields = (
            "organization",
            "status",
            "provider_reference",
            "created_at",
            "updated_at",
        )
