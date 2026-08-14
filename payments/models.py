from decimal import Decimal
import uuid
from django.db import models
from users.models import CustomUser
from organization.models import OrganizationBaseModel
from sales.models import Sale


class Payment(OrganizationBaseModel):
    class ReconciliationStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        MATCHED = "MATCHED", "Matched"
        MISMATCH = "MISMATCH", "Mismatch"

    class ProviderChoices(models.TextChoices):
        MPESA = "MPESA", "M-Pesa"
        MANUAL = "MANUAL", "Manual"

    class StatusChoices(models.TextChoices):
        INITIATED = "INITIATED", "Initiated"
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        REFUNDED = "REFUNDED", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    provider = models.CharField(
        max_length=20, choices=ProviderChoices.choices, default=ProviderChoices.MPESA
    )
    status = models.CharField(
        max_length=20, choices=StatusChoices.choices, default=StatusChoices.INITIATED
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="KES")
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    provider_reference = models.CharField(max_length=255, blank=True)
    merchant_reference = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True)
    failure_reason = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=5)
    next_retry_at = models.DateTimeField(blank=True, null=True)
    last_retry_at = models.DateTimeField(blank=True, null=True)
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING,
    )
    reconciled_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payments_created",
    )
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payments_updated",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} payment {self.id} ({self.status})"


class MpesaTransaction(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    result_code = models.CharField(max_length=20, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    mpesa_receipt_number = models.CharField(max_length=100, blank=True, null=True)
    # M-Pesa's own timestamp for the transaction. Previously auto_now_add, which
    # silently overwrote it with our receive time; reconciliation needs the real
    # value, so it is now set from the callback payload.
    transaction_date = models.DateTimeField(blank=True, null=True)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    # Why an inbound direct payment could not be auto-reconciled, so the pending
    # queue can explain itself to whoever resolves it by hand.
    reconciliation_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"MpesaTransaction {self.mpesa_receipt_number or self.checkout_request_id} ({self.phone_number})"


class Refund(OrganizationBaseModel):
    class StatusChoices(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name="refunds"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(
        max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING
    )
    reason = models.TextField(blank=True)
    provider_reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Refund {self.id} for payment {self.payment_id}"
