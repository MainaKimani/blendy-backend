import uuid
from django.db import models


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True)
    domain = models.CharField(max_length=255, blank=True, null=True)
    business_type = models.CharField(max_length=255, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tax_number = models.CharField(max_length=255, blank=True, null=True)
    subscription_plan = models.CharField(
        max_length=50,
        choices=[
            ("FREE", "Free"),
            ("BASIC", "Basic"),
            ("PREMIUM", "Premium"),
            ("ENTERPRISE", "Enterprise"),
        ],
        default="FREE",
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ("ACTIVE", "Active"),
            ("SUSPENDED", "Suspended"),
            ("CANCELLED", "Cancelled"),
        ],
        default="ACTIVE",
    )
    settings = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    subscription_expires_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name
