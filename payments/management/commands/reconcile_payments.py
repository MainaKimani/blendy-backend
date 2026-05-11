from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from payments.models import Payment


class Command(BaseCommand):
    help = "Reconcile pending/failed payments and handle retry exhaustion."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        due = Payment.objects.select_related("sale").filter(
            status__in=[Payment.StatusChoices.PENDING, Payment.StatusChoices.FAILED],
            next_retry_at__isnull=False,
            next_retry_at__lte=now,
        )

        retried = 0
        exhausted = 0
        for payment in due:
            if payment.retry_count >= payment.max_retries:
                payment.status = Payment.StatusChoices.CANCELLED
                payment.failure_reason = payment.failure_reason or "Retry limit reached"
                payment.sale.payment_status = "CANCELLED"
                payment.reconciliation_status = Payment.ReconciliationStatus.MISMATCH
                payment.reconciled_at = now
                payment.sale.save(update_fields=["payment_status"])
                payment.save(update_fields=["status", "failure_reason", "reconciliation_status", "reconciled_at", "updated_at"])
                exhausted += 1
                continue

            payment.reconciliation_status = Payment.ReconciliationStatus.PENDING
            payment.save(update_fields=["reconciliation_status", "updated_at"])
            retried += 1

        success = Payment.objects.filter(status=Payment.StatusChoices.SUCCEEDED).exclude(reconciliation_status=Payment.ReconciliationStatus.MATCHED)
        matched = success.update(
            reconciliation_status=Payment.ReconciliationStatus.MATCHED,
            reconciled_at=now,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Reconciliation done. due={due.count()} retried={retried} exhausted={exhausted} matched={matched}"
        ))
