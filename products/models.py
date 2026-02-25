import uuid
from django.db import models
from organization.models import Organization
from users.models import CustomUser


class OrganizationBaseModel(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Category(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Product(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=255, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="products_created",
    )

    def __str__(self):
        return self.name


class ProductImage(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} image"


class Currency(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    iso_code = models.CharField(max_length=3)
    numeric_code = models.CharField(max_length=3)
    symbol = models.CharField(max_length=5)

    def __str__(self):
        return self.name


class UOM(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    symbol = models.CharField(max_length=10)

    def __str__(self):
        return self.name


class ProductVariation(OrganizationBaseModel):
    SIZE_CHOICES = (
        ("xl", "Extra Large"),
        ("l", "Large"),
        ("m", "Medium"),
        ("s", "Small"),
        ("xs", "Extra Small"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variations"
    )
    sku = models.CharField(max_length=255, unique=True, blank=True, null=True)
    size = models.CharField(max_length=2, choices=SIZE_CHOICES, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, default=0, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True)
    uom = models.ForeignKey(UOM, on_delete=models.SET_NULL, null=True)
    color = models.CharField(max_length=50, blank=True)
    pack_size = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    measurement = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    size = models.CharField(max_length=2, choices=SIZE_CHOICES, null=True, blank=True)
    reorder_level = models.IntegerField(null=True, blank=True)
    barcode = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def name(self):
        parts = [self.product.name]
        if self.pack_size:
            parts.append(f"{self.pack_size}(pcs)")
        if self.color:
            parts.append(self.color)
        if self.size:
            parts.append(self.get_size_display())

        measurement_parts = []
        if self.measurement:
            measurement_parts.append(str(self.measurement))
        if self.uom:
            measurement_parts.append(self.uom.symbol)

        if measurement_parts:
            parts.append("".join(measurement_parts))

        return "-".join(parts)

    def __str__(self):
        return self.name
