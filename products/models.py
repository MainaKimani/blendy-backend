import uuid
import os
from io import BytesIO
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image

from organization.models import OrganizationBaseModel
from users.models import CustomUser


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
    tags = models.CharField(max_length=255, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    # A product carries no price: the pricelist is authoritative, and prices are
    # held per variation on PricelistItem.
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


# class ProductImage(OrganizationBaseModel):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     product = models.ForeignKey(
#         Product, on_delete=models.CASCADE, related_name="images"
#     )
#     image = models.ImageField(upload_to="products/")
#     alt_text = models.CharField(max_length=255, blank=True)
#     is_primary = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     def __str__(self):
#         return f"{self.product.name} image"


class ProductImage(OrganizationBaseModel):
    THUMBNAIL_SIZE = (300, 300)
    MAX_IMAGE_SIZE = (1920, 1080)
    COMPRESSION_QUALITY = 85  # JPEG quality (1-95)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/")
    thumbnail = models.ImageField(
        upload_to="products/thumbnails/", blank=True, null=True
    )
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} image"

    def save(self, *args, **kwargs):
        # Only process if there's a new image being uploaded
        if self.image and hasattr(self.image, "file"):
            self.image = self._compress_image(self.image)
            thumbnail_file = self._generate_thumbnail(self.image)
            if thumbnail_file:
                thumb_name = self._get_thumbnail_name(self.image.name)
                self.thumbnail.save(thumb_name, thumbnail_file, save=False)
        super().save(*args, **kwargs)

    def _compress_image(self, image_field):
        img = Image.open(image_field)

        # Convert to RGB if needed (e.g. PNG with transparency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize if larger than max dimensions (maintains aspect ratio)
        img.thumbnail(self.MAX_IMAGE_SIZE, Image.LANCZOS)

        output = BytesIO()
        img.save(output, format="JPEG", quality=self.COMPRESSION_QUALITY, optimize=True)
        output.seek(0)

        # Preserve the original filename but force .jpg extension
        original_name = os.path.splitext(image_field.name)[0]
        new_name = f"{original_name}.jpg"

        return ContentFile(output.read(), name=new_name)

    def _generate_thumbnail(self, image_field):
        try:
            img = Image.open(image_field)

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.thumbnail(self.THUMBNAIL_SIZE, Image.LANCZOS)

            output = BytesIO()
            img.save(
                output, format="JPEG", quality=self.COMPRESSION_QUALITY, optimize=True
            )
            output.seek(0)

            return ContentFile(output.read())
        except Exception:
            return None

    def _get_thumbnail_name(self, image_name):
        base = os.path.splitext(os.path.basename(image_name))[0]
        return f"{base}_thumb.jpg"


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
