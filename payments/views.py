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
from .models import Payment, Refund
from .serializers import PaymentSerializer, PaymentStatusUpdateSerializer, RefundSerializer
from .services.providers.factory import get_provider
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
        idempotency_key = self.request.headers.get("Idempotency-Key") or uuid.uuid4().hex
        charge = provider.create_charge(
            amount=serializer.validated_data["amount"],
            currency=serializer.validated_data.get("currency", "KES"),
            phone_number=serializer.validated_data.get("phone_number", ""),
            idempotency_key=idempotency_key,
        )
        serializer.save(
            created_by=user,
            updated_by=user,
            status=charge.status,
            provider_reference=charge.reference,
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

        provider_reference = request.data.get("provider_reference") or request.data.get("CheckoutRequestID")
        if not provider_reference:
            return Response({"detail": "provider_reference is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = Payment.objects.select_related("sale").get(provider_reference=provider_reference)
        except Payment.DoesNotExist:
            return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

        # MPESA success is usually ResultCode=0; keep aliases for flexibility.
        result_code = request.data.get("ResultCode")
        if str(result_code) in {"0", "SUCCESS", "SUCCEEDED"}:
            payment.status = Payment.StatusChoices.SUCCEEDED
            payment.sale.payment_status = "PAID"
            payment.paid_at = timezone.now()
            payment.failure_reason = ""
        else:
            payment.status = Payment.StatusChoices.FAILED
            payment.sale.payment_status = "FAILED"
            payment.failure_reason = request.data.get("ResultDesc", "Payment failed")

        payment.sale.save(update_fields=["payment_status"])
        payment.save(update_fields=["status", "paid_at", "failure_reason", "updated_at"])

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
            raise ValidationError("Refund amount cannot be greater than payment amount.")

        payment.status = Payment.StatusChoices.REFUNDED
        payment.sale.payment_status = "REFUNDED"
        payment.sale.save(update_fields=["payment_status"])
        payment.save(update_fields=["status", "updated_at"])
