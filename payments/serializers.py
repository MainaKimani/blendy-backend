from decimal import Decimal
import re

from django.utils import timezone
from rest_framework import serializers
from .models import MpesaTransaction, Payment, Refund


class MpesaTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MpesaTransaction
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class PaymentSerializer(serializers.ModelSerializer):
    SAFARICOM_PREFIXES = {
        "25470",
        "25471",
        "25472",
        "25474",
        "25474",
        "25475",
        "25476",
        "25477",
        "25479",
        "25410",
        "25411",
    }
    transactions = MpesaTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = (
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
        provider = attrs.get("provider")
        if not provider:
            raise serializers.ValidationError("Provider is required.")
        if provider == Payment.ProviderChoices.MPESA and not attrs.get("phone_number"):
            raise serializers.ValidationError(
                "Phone number is required for M-Pesa payments."
            )
        if attrs.get("phone_number"):
            normalized_phone = self._normalize_kenyan_phone(attrs.get("phone_number"))
            attrs["phone_number"] = normalized_phone

        if attrs.get("provider") == Payment.ProviderChoices.MPESA:
            self._validate_safaricom_phone(normalized_phone)

        if amount is not None and amount <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Payment amount must be greater than zero."
            )
        if sale and amount and amount != sale.total_amount:
            raise serializers.ValidationError(
                "Payment amount must equal the sale total amount. Expected: {}".format(
                    sale.total_amount
                )
            )
        return attrs

    def _normalize_kenyan_phone(self, phone_number: str | None) -> str:
        if not phone_number:
            raise serializers.ValidationError("Phone number is required for payments.")

        # Remove spaces, dashes and parentheses while preserving the leading + where present.
        cleaned = re.sub(r"[^\d+]", "", phone_number.strip())
        digits_only = cleaned.replace("+", "")

        if digits_only.startswith("0") and len(digits_only) == 10:
            digits_only = f"254{digits_only[1:]}"
        elif digits_only.startswith("254") and len(digits_only) == 12:
            pass
        elif digits_only.startswith("7") and len(digits_only) == 9:
            digits_only = f"254{digits_only}"
        elif digits_only.startswith("1") and len(digits_only) == 9:
            digits_only = f"254{digits_only}"
        else:
            raise serializers.ValidationError(
                "Enter a valid Kenyan phone number (e.g. +2547XXXXXXXX or 07XXXXXXXX)."
            )

        return f"+{digits_only}"

    def _validate_safaricom_phone(self, normalized_phone: str) -> None:
        digits = normalized_phone.replace("+", "")
        if digits[:5] not in self.SAFARICOM_PREFIXES:
            raise serializers.ValidationError(
                "M-Pesa payments require a Safaricom phone number."
            )


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
        elif status_value == Payment.StatusChoices.FAILED:
            payment.sale.payment_status = "FAILED"
        elif status_value == Payment.StatusChoices.CANCELLED:
            payment.sale.payment_status = "CANCELLED"

        payment.sale.save(update_fields=["payment_status"])
        payment.save()
        return payment


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = "__all__"
        read_only_fields = (
            "status",
            "provider_reference",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        amount = attrs.get("amount")
        payment = attrs.get("payment")

        if amount is None or amount <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Refund amount must be greater than zero."
            )

        if payment and amount > payment.amount:
            raise serializers.ValidationError(
                "Refund amount cannot be greater than payment amount."
            )

        return attrs
