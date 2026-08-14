from django.contrib import admin
from .models import Payment, Refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "status",
        "reconciliation_status",
        "amount",
        "retry_count",
        "next_retry_at",
        "created_at",
    )
    list_filter = ("provider", "status", "reconciliation_status", "created_at")
    search_fields = ("id", "provider_reference", "idempotency_key", "phone_number")
    ordering = ("-created_at",)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "status", "amount", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "payment__id", "provider_reference")
