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
    # Till/Paybill shortcode, used to route inbound M-Pesa C2B confirmations to
    # the right tenant. Null while a deployment runs a single shared shortcode.
    mpesa_shortcode = models.CharField(
        max_length=20, blank=True, null=True, unique=True
    )
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
    # Blendy's own HQ, not a customer. Flagged rather than matched by name or
    # slug so renaming it cannot silently turn it back into a tenant. At most
    # one may exist; the constraint below enforces that in the database rather
    # than by convention.
    is_platform = models.BooleanField(default=False)
    settings = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    subscription_expires_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_platform"],
                condition=models.Q(is_platform=True),
                name="only_one_platform_organization",
            )
        ]

    def __str__(self):
        return self.name


class OrganizationBaseModel(models.Model):
    """Base for every tenant-scoped model.

    Lives here, in the app that owns Organization, so there is a single
    definition of what "belongs to a tenant" means. Previously each app carried
    its own identical copy, which made it easy to add a model that looked
    tenanted but wasn't.

    Pair this with inventory.views.OrganizationBaseViewSet, which fails closed
    when a request carries no tenant.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class PlatformAccessLog(models.Model):
    """A record of Blendy staff reaching into a customer's data.

    Written whenever a request names one organization while the caller belongs
    to another — grants and denials alike, so an attempt that was refused is as
    visible as one that succeeded.

    Deliberately **not** an OrganizationBaseModel. It records access *to* a
    tenant by someone outside it; tenant-scoping it would put the subject of the
    record in charge of the record.

    Actor email and organization slug are denormalised on purpose. The point of
    this table is to answer "who looked at my data?" years later, and a foreign
    key alone stops answering that the moment the staff member's account is
    deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    actor = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_accesses",
    )
    actor_email = models.CharField(max_length=254)

    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_accesses",
    )
    organization_slug = models.CharField(max_length=255)

    # Whether the actor worked for Blendy at the time. Recorded rather than
    # derived, for the same reason the email is: the actor may later be deleted
    # or move organizations, and a record that changes its meaning afterwards is
    # not an audit trail.
    #
    # It is also what lets the tenant-facing view name Blendy staff — which is
    # the honest answer to "who looked at my data?" — while withholding the
    # identity of a *different tenant* whose access was refused. Naming them
    # would leak one customer's staff email to another, which is precisely the
    # boundary this log exists to watch.
    actor_is_platform = models.BooleanField(default=False)

    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    status_code = models.PositiveSmallIntegerField()
    # Derived from the status rather than asked of the permission layer, so a
    # view that authorises by some other route is still recorded honestly.
    granted = models.BooleanField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        verb = "accessed" if self.granted else "was refused"
        return f"{self.actor_email} {verb} {self.organization_slug} ({self.method} {self.path})"
