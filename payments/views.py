import datetime
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser
from .models import MpesaTransaction, Payment, Refund
from .serializers import (
    PaymentSerializer,
    PaymentStatusUpdateSerializer,
    RefundSerializer,
)
from .services.providers.factory import get_provider
from .services.ops.retry import schedule_next_retry
from .services.webhooks.signature import InvalidWebhookSignature, verify_mpesa_signature


class PaymentViewSet(OrganizationBaseViewSet):
    queryset = Payment.objects.select_related("sale")
    serializer_class = PaymentSerializer

    def get_permissions(self):
        return []

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        # Resolve provider adapter so creation logic remains gateway-agnostic.
        provider = get_provider(serializer.validated_data["provider"])
        # Idempotency header allows safe client retries for payment create requests.
        idempotency_key = (
            self.request.headers.get("Idempotency-Key") or uuid.uuid4().hex
        )
        try:
            charge = provider.create_charge(
                amount=serializer.validated_data["amount"],
                currency=serializer.validated_data.get("currency", "KES"),
                phone_number=serializer.validated_data.get("phone_number", ""),
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        serializer.save(
            created_by=user,
            updated_by=user,
            status=charge.status,
            provider_reference=charge.provider_reference,
            merchant_reference=charge.merchant_reference,
            idempotency_key=idempotency_key,
        )

    @action(detail=True, methods=["post"], url_path="update-status")
    @transaction.atomic
    def update_status(self, request, pk=None):
        payment = self.get_object()
        serializer = PaymentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = serializer.update_payment(payment)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)


class MpesaWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # Webhooks are unauthenticated; signature verification is the trust boundary.
        signature = request.headers.get("X-Mpesa-Signature", "")
        try:
            verify_mpesa_signature(request.body, signature)
        except InvalidWebhookSignature as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data.get("Body", {}).get("stkCallback", {})
        if not payload:
            raise ValueError("Invalid MPESA webhook payload: missing Body.stkCallback")
        metadata = payload.get("CallbackMetadata")
        if metadata and "Item" in metadata:
            items = metadata["Item"]
            # Use a dictionary comprehension to flatten the 'Item' list into a single dictionary
            parsed_data = {item["Name"]: item.get("Value") for item in items}

        provider_reference = payload.get("CheckoutRequestID")
        if not provider_reference:
            return Response(
                {"detail": "provider_reference is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.select_related("sale").get(
                provider_reference=provider_reference
            )
        except Payment.DoesNotExist:
            return Response(
                {"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        MpesaTransaction.objects.create(
            merchant_request_id=payload.get("MerchantRequestID", ""),
            checkout_request_id=payload.get("CheckoutRequestID", ""),
            phone_number=parsed_data.get("PhoneNumber") if metadata else None,
            amount=parsed_data.get("Amount") if metadata else None,
            result_code=payload.get("ResultCode"),
            description=payload.get("ResultDesc", ""),
            mpesa_receipt_number=(
                parsed_data.get("MpesaReceiptNumber") if metadata else None
            ),
            payment=payment,
        )

        # MPESA success is usually ResultCode=0; keep aliases for flexibility.
        result_code = payload.get("ResultCode")
        if str(result_code) in {"0", "SUCCESS", "SUCCEEDED"}:
            payment.status = Payment.StatusChoices.SUCCEEDED
            payment.sale.payment_status = "PAID"
            payment.paid_at =  timezone.now()
            payment.failure_reason = ""
            payment.reconciliation_status = Payment.ReconciliationStatus.MATCHED
            payment.reconciled_at = timezone.now()
            payment.next_retry_at = None
        else:
            payment.status = Payment.StatusChoices.FAILED
            payment.sale.payment_status = "FAILED"
            payment.failure_reason = payload.get("ResultDesc")
            payment.reconciliation_status = Payment.ReconciliationStatus.MISMATCH

        payment.sale.save(update_fields=["payment_status"])
        payment.save(
            update_fields=[
                "status",
                "paid_at",
                "failure_reason",
                "reconciliation_status",
                "reconciled_at",
                "next_retry_at",
                "updated_at",
            ]
        )
        if (
            payment.status == Payment.StatusChoices.FAILED
            and payment.retry_count < payment.max_retries
        ):
            schedule_next_retry(payment)

        return Response({"detail": "Webhook processed"}, status=status.HTTP_200_OK)


class RefundViewSet(OrganizationBaseViewSet):
    queryset = Refund.objects.select_related("payment")
    serializer_class = RefundSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]

    @transaction.atomic
    def perform_create(self, serializer):
        refund = serializer.save()
        payment = refund.payment
        if refund.amount > payment.amount:
            raise ValidationError(
                "Refund amount cannot be greater than payment amount."
            )

        payment.status = Payment.StatusChoices.REFUNDED
        payment.sale.payment_status = "REFUNDED"
        payment.sale.save(update_fields=["payment_status"])
        payment.save(update_fields=["status", "updated_at"])
