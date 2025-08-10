import uuid
from django.db import models
from users.models import CustomUser
from products.models import Product, OrganizationBaseModel, ProductVariation

class Sale(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255, blank=True, null=True)
    sale_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='sales_created')
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='sales_updated')

    @property
    def total_amount(self):
        return sum(item.total_price for item in self.items.all())

    def __str__(self):
        return f"Sale {self.id} - {self.total_amount}"

class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product_variation.name} in Sale {self.sale.id}"
