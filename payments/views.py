from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser
from .models import Payment, Refund
from .serializers import (
    PaymentSerializer,
    PaymentStatusUpdateSerializer,
    RefundSerializer,
)


class PaymentViewSet(OrganizationBaseViewSet):
    queryset = Payment.objects.select_related("sale")
    serializer_class = PaymentSerializer

    def get_permissions(self):
        # return [IsAuthenticated(), IsOrganizationUser()]
        return []

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(
            created_by=user,
            updated_by=user,
            status=Payment.StatusChoices.PENDING,
        )

    @action(detail=True, methods=["post"], url_path="update-status")
    @transaction.atomic
    def update_status(self, request, pk=None):
        payment = self.get_object()
        serializer = PaymentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = serializer.update_payment(payment)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)


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
