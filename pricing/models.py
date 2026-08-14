import uuid
from django.db import models
from organization.models import OrganizationBaseModel
from products.models import ProductVariation


class Pricelist(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    # Every organization gets one at onboarding, named "Default Pricelist". It is
    # what sales are priced from, so an organization without one cannot transact.
    # Flagged rather than matched by name, so renaming it does not break pricing.
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class PricelistItem(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pricelist = models.ForeignKey(
        Pricelist, on_delete=models.CASCADE, related_name="items"
    )
    # Pricing is per sellable unit, and the variation is the sellable unit, so
    # a price applies to a variation rather than to the parent product.
    product_variation = models.ForeignKey(
        ProductVariation,
        on_delete=models.CASCADE,
        related_name="pricelist_items",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product_variation} - {self.pricelist.name} - {self.price}"

    class Meta:
        unique_together = ("pricelist", "product_variation")
        # Deterministic order so paginated listings are stable between requests.
        ordering = ["-created_at"]
