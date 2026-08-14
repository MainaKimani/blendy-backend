from decimal import Decimal
import uuid
from django.db import models
from users.models import CustomUser
from organization.models import OrganizationBaseModel
from products.models import ProductVariation


class Sale(OrganizationBaseModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("UNPAID", "Unpaid"),
        ("FAILED", "Failed"),
        # Set when an STK push fails or times out. The sale stays open so the
        # customer can pay directly to the Till and the incoming C2B payment can
        # be reconciled against it (MVP §8, US-9b/9c). Deliberately distinct from
        # FAILED, which is terminal.
        ("AWAITING_DIRECT_PAYMENT", "Awaiting Direct Payment"),
        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled"),
        ("REFUNDED", "Refunded"),
    ]

    # Statuses a direct M-Pesa payment may be matched against.
    OPEN_FOR_DIRECT_PAYMENT = ("AWAITING_DIRECT_PAYMENT",)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    shipping_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    payment_status = models.CharField(
        max_length=30, choices=PAYMENT_STATUS_CHOICES, default="UNPAID"
    )
    # Customer Details (For guest checkout)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)

    # The list this sale was priced from. Recorded so the sale still explains its
    # own prices after the list is edited. Null only on sales that predate
    # pricelists being authoritative.
    pricelist = models.ForeignKey(
        "pricing.Pricelist",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="sales_created"
    )
    updated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="sales_updated"
    )

    class Meta:
        # Deterministic order so paginated listings are stable between requests.
        ordering = ["-created_at"]

    @property
    def total_amount(self):
        return (
            sum((item.total_price for item in self.items.all()), Decimal("0.00"))
            + self.shipping_fee
        )

    def __str__(self):
        return f"Sale {self.id} - {self.total_amount}"


class SaleItem(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    # The variation is the sellable unit: it is what carries stock, so it is what
    # a sale line must point at. PROTECT because deleting a variation must never
    # silently delete the sales history that references it.
    product_variation = models.ForeignKey(
        ProductVariation,
        on_delete=models.PROTECT,
        related_name="sale_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    # The three price fields are recorded together so a line is self-explaining
    # and tamper-evident, and all three are per unit:
    #   unit_price    - the pricelist price at the time of sale
    #   discount      - the concession granted, per unit
    #   selling_price - what was actually charged = unit_price - discount
    #   cost_price    - what the item cost us, snapshotted at the time of sale
    # total_price is then quantity * selling_price. The relationship is verified
    # exactly on write, so a line can never silently disagree with itself. All
    # four are snapshots: later edits to the pricelist or the variation's cost
    # must not rewrite what a past sale says.
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_variation.name} in Sale {self.sale.id}"
