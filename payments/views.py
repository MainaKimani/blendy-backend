import datetime
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser
from .models import MpesaTransaction, Payment, Refund
from .serializers import (
    MpesaTransactionSerializer,
    PaymentSerializer,
    PaymentStatusUpdateSerializer,
    RefundSerializer,
)
from .throttles import STKPushIPThrottle, STKPushPhoneThrottle
from .services.providers.factory import get_provider
from .services.ops.retry import schedule_next_retry
from .services.reconciliation import (
    TenantNotResolved,
    parse_mpesa_timestamp,
    reconcile_direct_payment,
    resolve_organization,
)
from .services.webhooks.security import (
    WebhookAuthenticationFailed,
    authenticate_mpesa_callback,
)
from .services.webhooks.signature import InvalidWebhookSignature, verify_mpesa_signature


class PaymentViewSet(OrganizationBaseViewSet):
    queryset = Payment.objects.select_related("sale")
    serializer_class = PaymentSerializer

    def get_permissions(self):
        # Guest checkout has to be able to pay for its own sale, so create stays
        # open; everything that reads or mutates existing payments does not.
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationUser()]

    def get_throttles(self):
        # Anonymous creates trigger an STK push to a caller-supplied number, so
        # they are rate limited. Authenticated staff running a till are not.
        if self.action == "create" and not self.request.user.is_authenticated:
            return [STKPushPhoneThrottle(), STKPushIPThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer):
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to create a payment."
            )
        sale = serializer.validated_data["sale"]
        if sale.organization_id != organization.id:
            # Without this the sale FK is an unguarded cross-tenant reference.
            raise PermissionDenied("Sale does not belong to this organization.")

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
            organization=organization,
            created_by=user,
            updated_by=user,
            status=charge.status,
            provider_reference=charge.provider_reference,
            merchant_reference=charge.merchant_reference,
            idempotency_key=idempotency_key,
        )

    @action(detail=False, methods=["get"], url_path="unmatched")
    def unmatched(self, request):
        """Direct payments that arrived but could not be matched (US-10).

        These are not dropped: they stay here with a note explaining why, for
        an owner to reconcile by hand.
        """
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to list payments."
            )
        queryset = MpesaTransaction.objects.filter(
            organization=organization, payment__isnull=True
        )
        page = self.paginate_queryset(queryset)
        serializer = MpesaTransactionSerializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
    def post(self, request, token="", *args, **kwargs):
        # Safaricom does not sign callbacks, so the trust boundary is the secret
        # URL token plus the source-IP allowlist.
        try:
            authenticate_mpesa_callback(request, token)
        except WebhookAuthenticationFailed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        # Defence in depth for the MANUAL provider's test harness, which can
        # sign its requests even though Safaricom cannot.
        signature = request.headers.get("X-Mpesa-Signature", "")
        if signature:
            try:
                verify_mpesa_signature(request.body, signature)
            except InvalidWebhookSignature as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED
                )

        payload = request.data.get("Body", {}).get("stkCallback", {})
        if not payload:
            # A malformed body must not 500, or Safaricom will keep retrying it.
            return Response(
                {"detail": "Invalid MPESA webhook payload: missing Body.stkCallback"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed_data = {}
        metadata = payload.get("CallbackMetadata")
        if metadata and "Item" in metadata:
            # Flatten the 'Item' list into a single dictionary
            parsed_data = {
                item["Name"]: item.get("Value")
                for item in metadata["Item"]
                if "Name" in item
            }

        provider_reference = payload.get("CheckoutRequestID")
        merchant_reference = payload.get("MerchantRequestID")
        if not provider_reference:
            return Response(
                {"detail": "provider_reference is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not merchant_reference:
            return Response(
                {"detail": "merchant_reference is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = Payment.objects.select_related("sale").get(
                provider_reference=provider_reference,
                merchant_reference=merchant_reference,
            )
        except Payment.DoesNotExist:
            return Response(
                {"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND
            )

        MpesaTransaction.objects.create(
            organization=payment.organization,
            merchant_request_id=payload.get("MerchantRequestID", ""),
            checkout_request_id=payload.get("CheckoutRequestID", ""),
            phone_number=parsed_data.get("PhoneNumber"),
            amount=parsed_data.get("Amount"),
            result_code=payload.get("ResultCode"),
            description=payload.get("ResultDesc", ""),
            mpesa_receipt_number=parsed_data.get("MpesaReceiptNumber"),
            transaction_date=parse_mpesa_timestamp(parsed_data.get("TransactionDate")),
            payment=payment,
        )

        # MPESA success is usually ResultCode=0; keep aliases for flexibility.
        result_code = payload.get("ResultCode")
        if str(result_code) in {"0", "SUCCESS", "SUCCEEDED"}:
            paid_amount = parsed_data.get("Amount")
            expected_amount = payment.amount
            amount_matches = paid_amount is not None and Decimal(
                str(paid_amount)
            ) == Decimal(expected_amount)

            if not amount_matches:
                # A success callback for the wrong amount must never mark the
                # sale paid; flag it for manual review instead.
                payment.status = Payment.StatusChoices.PENDING
                payment.failure_reason = (
                    f"Callback amount {paid_amount} does not match expected "
                    f"{expected_amount}"
                )
                payment.reconciliation_status = Payment.ReconciliationStatus.MISMATCH
                payment.reconciled_at = timezone.now()
                payment.sale.payment_status = "UNPAID"
            else:
                payment.status = Payment.StatusChoices.SUCCEEDED
                payment.sale.payment_status = "PAID"
                payment.paid_at = timezone.now()
                payment.failure_reason = ""
                payment.reconciliation_status = Payment.ReconciliationStatus.MATCHED
                payment.reconciled_at = timezone.now()
                payment.next_retry_at = None
        else:
            payment.status = Payment.StatusChoices.FAILED
            # The push failed, but the sale must stay open so the customer can
            # pay the Till directly and be reconciled (MVP §8, US-9b).
            payment.sale.payment_status = "AWAITING_DIRECT_PAYMENT"
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


class MpesaC2BConfirmationView(APIView):
    """Receives unsolicited direct payments to the Till (MVP §8, US-9c).

    Separate from the STK callback: a direct payment has no CheckoutRequestID or
    MerchantRequestID, so it is attributed by shortcode and matched to an open
    sale by payer phone number and amount.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request, token="", *args, **kwargs):
        try:
            authenticate_mpesa_callback(request, token)
        except WebhookAuthenticationFailed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data or {}
        provider_reference = payload.get("TransID")
        if not provider_reference:
            return Response(
                {"detail": "TransID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            organization = resolve_organization(payload.get("BusinessShortCode"))
        except TenantNotResolved as exc:
            # 200 so Safaricom stops retrying a payment we structurally cannot
            # attribute; it is logged on their side and needs operator setup.
            return Response(
                {"ResultCode": 0, "ResultDesc": "Accepted", "detail": str(exc)},
                status=status.HTTP_200_OK,
            )

        mpesa_transaction = reconcile_direct_payment(
            organization=organization,
            phone_number=payload.get("MSISDN"),
            amount=payload.get("TransAmount"),
            provider_reference=provider_reference,
            transaction_date=parse_mpesa_timestamp(payload.get("TransTime")),
            raw_description=payload.get("TransactionType", ""),
        )

        # Safaricom expects this acknowledgement shape regardless of whether we
        # could match the payment; an unmatched one is queued, not rejected.
        return Response(
            {
                "ResultCode": 0,
                "ResultDesc": "Accepted",
                "matched": mpesa_transaction.payment_id is not None,
            },
            status=status.HTTP_200_OK,
        )


class RefundViewSet(OrganizationBaseViewSet):
    queryset = Refund.objects.select_related("payment")
    serializer_class = RefundSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]

    @transaction.atomic
    def perform_create(self, serializer):
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to create a refund."
            )
        if serializer.validated_data["payment"].organization_id != organization.id:
            raise PermissionDenied("Payment does not belong to this organization.")

        refund = serializer.save(organization=organization)
        payment = refund.payment
        if refund.amount > payment.amount:
            raise ValidationError(
                "Refund amount cannot be greater than payment amount."
            )

        payment.status = Payment.StatusChoices.REFUNDED
        payment.sale.payment_status = "REFUNDED"
        payment.sale.save(update_fields=["payment_status"])
        payment.save(update_fields=["status", "updated_at"])
