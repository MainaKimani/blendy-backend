"""The permission catalogue and the roles built from it.

The RBAC models have always existed, but nothing ever created a `Permission`
row — so `HasUserPermission` matched nothing and every guarded endpoint refused
everyone, including the shop owner who had just been onboarded as ORG_ADMIN.
This module is the missing catalogue.

It is **data, not schema**. `sync_rbac()` applies it and is idempotent, so it is
safe to run repeatedly: it creates what is missing and re-points each role's
permission set at what is declared here. A migration applies it on `migrate`,
and `manage.py seed_rbac` re-applies it after this file changes.

Adding a permission means adding it here and running the command. Nothing else
reads the strings, so a permission that no view checks is inert rather than
wrong — which is why a few forward-looking ones (reports, voids) are declared
before the endpoints that will check them exist. The point of declaring them
early is that the *cashier restriction* in US-15 is defined by what a cashier
must **not** hold, and you cannot withhold a permission that has no name.
"""

# --- The catalogue -----------------------------------------------------------
#
# Named `app.action_model`, matching Django's own convention and the strings
# already hard-coded in the viewsets.

CATALOGUE = {
    "products": {
        "product": "products",
        "productvariation": "product variations",
        "category": "product categories",
        "productimage": "product images",
        "uom": "units of measure",
        "currency": "currencies",
    },
    "pricing": {
        "pricelist": "pricelists",
        "pricelistitem": "prices on a pricelist",
    },
    "inventory": {
        "inventoryitem": "stock balances",
        "stockmovement": "the stock ledger",
        "location": "stock locations",
        "stocktake": "stock takes",
        "stocktakeitem": "stock take lines",
    },
    "sales": {
        "sale": "sales",
        "saleitem": "sale lines",
    },
    "payments": {
        "payment": "payments",
        "refund": "refunds",
    },
    "users": {
        "customuser": "staff accounts",
    },
    "authorization": {
        "organizationrole": "the roles this shop has enabled",
        "userroleassignment": "who holds which role",
    },
}

ACTIONS = {
    "view": "View",
    "add": "Create",
    "change": "Edit",
    "delete": "Delete",
}

# Actions that are not plain CRUD. Stock movement is the clearest case: the
# ledger is append-only and is written through dedicated endpoints, so
# "can move stock" is a different question from "can edit a StockMovement row".
EXTRA_PERMISSIONS = {
    "inventory.restock_stock": "Record stock arriving",
    "inventory.adjust_stock": "Correct a stock figure",
    "inventory.view_lowstock": "See the low-stock queue",
    "payments.reconcile_payment": "Match or override a payment by hand",
    "sales.void_sale": "Void a sale (US-20, not yet implemented)",
    "organization.view_access_log": (
        "See who outside this organization accessed its data"
    ),
    "reports.view_sales_report": "See sales and revenue reports (US-13/14, not yet implemented)",
    "reports.view_margin_report": "See cost and margin reports (US-14, not yet implemented)",
}


# Permissions held by Blendy's own staff, never by a shop's.
#
# Kept in a separate pool from the tenant catalogue for one reason: ORG_ADMIN is
# derived as "everything in the catalogue", so anything added to that pool lands
# on every shop owner. A shop owner holding platform.access_tenants would be
# able to read every other shop in the deployment.
PLATFORM_PERMISSIONS = {
    "platform.access_tenants": (
        "Read another organization's data. The gate for support work; the "
        "ordinary per-model permissions still decide what is visible."
    ),
    "platform.act_as_tenant": (
        "Write to another organization's data. Deliberately separate from "
        "access_tenants, so a support role can look without touching."
    ),
    "platform.onboard_organization": "Create a new customer organization",
    "platform.manage_platform_staff": "Add and remove Blendy staff",
    "platform.view_access_log": "See who accessed which organization",
}


def tenant_permission_names():
    """Permissions that belong to running a shop.

    This is what ORG_ADMIN holds. It must never include a `platform.*` name.
    """
    names = []
    for app_label, models in CATALOGUE.items():
        for model in models:
            for action in ACTIONS:
                names.append(f"{app_label}.{action}_{model}")
    names.extend(EXTRA_PERMISSIONS)
    return names


def platform_permission_names():
    """Permissions that belong to operating the platform."""
    return list(PLATFORM_PERMISSIONS)


def permission_names():
    """Every permission that should exist as a row, tenant and platform alike."""
    return tenant_permission_names() + platform_permission_names()


def describe(name):
    if name in PLATFORM_PERMISSIONS:
        return PLATFORM_PERMISSIONS[name]
    if name in EXTRA_PERMISSIONS:
        return EXTRA_PERMISSIONS[name]
    app_label, rest = name.split(".", 1)
    action, model = rest.split("_", 1)
    return f"{ACTIONS[action]} {CATALOGUE[app_label][model]}"


# --- The roles ---------------------------------------------------------------

ORG_ADMIN = "ORG_ADMIN"
CASHIER = "CASHIER"
VIEWER = "VIEWER"

# Blendy's own staff. These roles are enabled on the platform organization only.
PLATFORM_ADMIN = "PLATFORM_ADMIN"
SUPPORT_AGENT = "SUPPORT_AGENT"


def _org_admin_permissions():
    """The shop owner holds everything.

    Deliberately derived rather than listed: a permission added to the catalogue
    and forgotten in this list would lock the owner out of their own shop, which
    is the exact failure this module exists to fix.

    Derived from the *tenant* pool only. A shop owner must never hold a
    `platform.*` permission — that would let them read every other shop.
    """
    return set(tenant_permission_names())


def _cashier_permissions():
    """US-15: record sales and see stock — nothing else.

    > "Given a cashier-role user logs in, they should be able to record sales
    >  and view current stock, but not access revenue reports, edit product
    >  prices, or manage other users."

    So: sell, take payment, read the catalogue and the stock position. No
    pricing writes, no user management, no reports, no voids — a void reverses
    a sale and its stock, which is an owner's decision.
    """
    return {
        # Sell.
        "sales.view_sale",
        "sales.add_sale",
        "sales.view_saleitem",
        "sales.add_saleitem",
        # Take payment, but not reconcile one by hand.
        "payments.view_payment",
        "payments.add_payment",
        # Read the catalogue. Note view_pricelist* is included and the
        # add/change/delete counterparts are not: a cashier must be able to see
        # what something costs in order to sell it, and must not be able to
        # change it.
        "products.view_product",
        "products.view_productvariation",
        "products.view_category",
        "products.view_productimage",
        "products.view_uom",
        "products.view_currency",
        "pricing.view_pricelist",
        "pricing.view_pricelistitem",
        # See the stock position, including what needs reordering.
        "inventory.view_inventoryitem",
        "inventory.view_stockmovement",
        "inventory.view_location",
        "inventory.view_lowstock",
    }


def _viewer_permissions():
    """Browse the catalogue. Nothing else.

    This role is handed out by `/api/users/register/`, which is open to
    anonymous callers and needs only an organization id — so anyone who learns a
    shop's UUID can obtain it. Its scope is set by that fact, not by what the
    word "viewer" might suggest elsewhere.

    Deliberately excluded:

    * **Sales, payments, stock.** A self-registered stranger must not be able to
      read the shop's takings or its stock position.
    * **Pricelists.** Tempting to include, since `/api/products/` already exposes
      the default price anonymously — but only the *default* one. An
      organization running a second list (wholesale, staff) would leak it
      through `/api/pricing/pricelist-items/`, which is a class of information
      that is not otherwise public.

    What remains is the catalogue, which `/api/products/` already serves to
    anonymous callers. So this role grants nothing today that is not already
    public: it is what makes registration's role assignment work as written,
    and it becomes meaningful the moment catalogue reads are gated.
    """
    return {
        "products.view_product",
        "products.view_productvariation",
        "products.view_category",
        "products.view_productimage",
        "products.view_uom",
        "products.view_currency",
    }


def _support_agent_permissions():
    """Read a shop's data to help them, and change nothing.

    Two things combine here, and neither works alone:

    * `platform.access_tenants` is the gate — without it IsOrganizationUser
      refuses, because a Blendy employee is not a member of the shop.
    * The tenant `view_*` set is what they can see once across that boundary.

    Read-only falls out for free rather than being enforced separately: this
    role holds no `add_`, `change_` or `delete_` permission and no
    `platform.act_as_tenant`, so the ordinary per-action checks refuse every
    write without any support-specific code.

    Derived from the catalogue so a newly added model becomes visible to support
    automatically, which is the safe direction — the alternative is a support
    agent who cannot see the thing a shop is calling about.
    """
    return {"platform.access_tenants"} | {
        name for name in tenant_permission_names() if ".view_" in name
    }


def _platform_admin_permissions():
    """Blendy staff who can act, not only look.

    Holds the whole platform pool *and* the whole tenant pool: this is the
    delegable equivalent of the is_superuser_admin flag, and the point of it is
    that it can be granted and revoked per person and shows up in the access log.
    """
    return set(platform_permission_names()) | set(tenant_permission_names())


ROLES = {
    ORG_ADMIN: {
        "description": "Shop owner. Full access within their own organization.",
        "permissions": _org_admin_permissions,
    },
    CASHIER: {
        "description": (
            "Records sales and takes payment. Cannot change prices, manage "
            "staff, or see reports (US-15)."
        ),
        "permissions": _cashier_permissions,
    },
    VIEWER: {
        "description": (
            "Browses the product catalogue. Assigned automatically by "
            "self-registration, which is open, so it holds nothing that is not "
            "already public."
        ),
        "permissions": _viewer_permissions,
    },
    SUPPORT_AGENT: {
        "description": (
            "Blendy support. Reads any organization's data to answer a "
            "question, and can change nothing."
        ),
        "permissions": _support_agent_permissions,
    },
    PLATFORM_ADMIN: {
        "description": (
            "Blendy platform administrator. Onboards organizations, manages "
            "Blendy staff, and can act inside any organization."
        ),
        "permissions": _platform_admin_permissions,
    },
}

# Enabled for every organization at onboarding, so an owner can hire a cashier
# without first having to enable the role by hand, and so self-registration has
# a VIEWER role to assign.
DEFAULT_ORGANIZATION_ROLES = (ORG_ADMIN, CASHIER, VIEWER)

# Enabled on the platform organization *only*. Enabling either of these on a
# shop would hand that shop's staff a key to every other shop, so they are kept
# out of DEFAULT_ORGANIZATION_ROLES rather than filtered out later.
PLATFORM_ROLES = (PLATFORM_ADMIN, SUPPORT_AGENT)


# --- Applying it -------------------------------------------------------------


def sync_rbac(apps=None):
    """Create the catalogue and point each role at its declared permissions.

    Idempotent. Safe to run on every deploy. Returns a summary dict.

    `apps` accepts a migration's historical registry; without it the real models
    are used. Permissions are never deleted — a name that disappears from the
    catalogue may still be referenced by a role someone created by hand, and
    silently dropping it would revoke access without saying so. Roles declared
    here do have their permission set replaced, since that set is the whole
    point of declaring them.
    """
    if apps is None:
        from .models import Permission, Role
    else:
        Permission = apps.get_model("authorization", "Permission")
        Role = apps.get_model("authorization", "Role")

    created_permissions = 0
    permissions = {}
    for name in permission_names():
        permission, created = Permission.objects.get_or_create(
            name=name, defaults={"description": describe(name)}
        )
        permissions[name] = permission
        created_permissions += int(created)

    created_roles = 0
    for role_name, spec in ROLES.items():
        role, created = Role.objects.get_or_create(
            name=role_name, defaults={"description": spec["description"]}
        )
        created_roles += int(created)
        role.permissions.set(
            [permissions[name] for name in sorted(spec["permissions"]())]
        )

    return {
        "permissions_total": len(permissions),
        "permissions_created": created_permissions,
        "roles_total": len(ROLES),
        "roles_created": created_roles,
    }


def enable_default_roles(apps=None):
    """Enable the built-in roles for every existing organization.

    Onboarding does this for new shops. Existing ones need it applied to them,
    and need it applied again whenever a role is added to
    DEFAULT_ORGANIZATION_ROLES — otherwise the new role exists globally but is
    enabled nowhere, which looks identical to it not being seeded at all.

    Idempotent. Returns the number of links created.
    """
    if apps is None:
        from organization.models import Organization

        from .models import OrganizationRole, Role
    else:
        Organization = apps.get_model("organization", "Organization")
        OrganizationRole = apps.get_model("authorization", "OrganizationRole")
        Role = apps.get_model("authorization", "Role")

    # HQ is not a shop. Enabling CASHIER and VIEWER on it would be harmless but
    # incoherent — an organization that looks like it might sell something.
    #
    # Guarded rather than filtered unconditionally, because this runs from
    # migrations that predate the is_platform field. At that point in history
    # every organization is a tenant, so the filter would be a no-op anyway —
    # but referencing a column that does not exist yet is a FieldError.
    organizations = Organization.objects.all()
    if any(f.name == "is_platform" for f in Organization._meta.get_fields()):
        organizations = organizations.filter(is_platform=False)

    roles = [
        role
        for role in (
            Role.objects.filter(name=name).first()
            for name in DEFAULT_ORGANIZATION_ROLES
        )
        if role is not None
    ]

    created = 0
    for organization in organizations:
        for role in roles:
            _, was_created = OrganizationRole.objects.get_or_create(
                organization=organization, role=role
            )
            created += int(was_created)
    return created


def enable_platform_roles(apps=None):
    """Enable the platform roles on the HQ organization, and nowhere else.

    Separate from `enable_default_roles` on purpose. That one walks every
    customer; this one targets exactly one organization, because enabling
    SUPPORT_AGENT on a shop would hand that shop's staff a key to every other
    shop in the deployment.

    Idempotent. Returns the number of links created, or 0 if HQ does not exist
    yet — the roles still exist globally and can be enabled once it does.
    """
    if apps is None:
        from organization.models import Organization

        from .models import OrganizationRole, Role
    else:
        Organization = apps.get_model("organization", "Organization")
        OrganizationRole = apps.get_model("authorization", "OrganizationRole")
        Role = apps.get_model("authorization", "Role")

    platform = Organization.objects.filter(is_platform=True).first()
    if platform is None:
        return 0

    created = 0
    for name in PLATFORM_ROLES:
        role = Role.objects.filter(name=name).first()
        if role is None:
            continue
        _, was_created = OrganizationRole.objects.get_or_create(
            organization=platform, role=role
        )
        created += int(was_created)
    return created
