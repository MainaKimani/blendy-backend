import uuid
from django.db import models
from organization.models import Organization
from users.models import CustomUser
from products.models import Product, Category, ProductVariation

class OrganizationBaseModel(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        abstract = True

class AgentInventoryItem(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='inventory_items')
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE, related_name='agent_inventory')
    quantity = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('agent', 'product_variation')
        verbose_name = "Agent Inventory Item"
        verbose_name_plural = "Agent Inventory Items"

    def __str__(self):
        return f"{self.quantity} x {self.product_variation.name} for {self.agent.username}"

class Location(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, unique=True)
    address = models.TextField(blank=True)
    region = models.CharField(max_length=255, blank=True)
    contact_person = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class InventoryItem(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    available_quantity = models.IntegerField(default=0)
    picked_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='inventory_items_updated')

    class Meta:
        unique_together = ('product_variation', 'location')

    def __str__(self):
        return f'{self.product_variation.name} at {self.location.name}'

class StockMovement(OrganizationBaseModel):
    MOVEMENT_TYPES = (
        ('STOCK_IN', 'Stock In'),
        ('STOCK_OUT', 'Stock Out'),
        ('TRANSFER', 'Transfer'),
        ('ADJUSTMENT', 'Adjustment'),
        ('PICK', 'Pick'),
        ('UNPICK', 'Unpick'),
        ('SALE', 'Sale'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference_number = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    movement_date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='stock_movements_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.movement_type} of {self.quantity} x {self.product_variation.name}'

class StockTake(OrganizationBaseModel):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(max_length=255, unique=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    scheduled_date = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, related_name='stock_takes_created')
    completed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_takes_completed')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference_number

class StockTakeItem(OrganizationBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock_take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name='items')
    product_variation = models.ForeignKey(ProductVariation, on_delete=models.CASCADE)
    system_quantity = models.IntegerField()
    counted_quantity = models.IntegerField()
    variance = models.IntegerField()
    notes = models.TextField(blank=True)
    counted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_take_items_counted')
    counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('stock_take', 'product_variation')

    def __str__(self):
        return f'{self.product_variation.name} in {self.stock_take.reference_number}'
