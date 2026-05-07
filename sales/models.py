from decimal import Decimal
import uuid
from django.db import models
from users.models import CustomUser
from products.models import Product, OrganizationBaseModel


class Sale(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("UNPAID", "Unpaid"),
        ("PAID", "Paid"),
        ("REFUNDED", "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    shipping_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="UNPAID"
    )
    # Customer Details (For guest checkout)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="sales_created"
    )
    updated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, related_name="sales_updated"
    )

    @property
    def total_amount(self):
        return (
            sum((item.total_price for item in self.items.all()), Decimal("0.00"))
            + self.shipping_fee
        )

    def __str__(self):
        return f"Sale {self.id} - {self.total_amount}"


class SaleItem(models.Model):
    SIZE_CHOICES = [
        ("xs", "Extra Small"),
        ("s", "Small"),
        ("m", "Medium"),
        ("l", "Large"),
        ("xl", "Extra Large"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product",
    )
    size_variation = models.CharField(
        max_length=2, choices=SIZE_CHOICES, blank=True, null=True
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name} {self.size_variation} in Sale {self.sale.id}"
