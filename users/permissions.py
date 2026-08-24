from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework import permissions

# Which permission verb each viewset action requires. Anything not listed —
# a custom @action, for instance — is treated as a read unless the caller says
# otherwise, since that is the safe direction to guess in.
CRUD_ACTIONS = {
    "list": "view",
    "retrieve": "view",
    "create": "add",
    "update": "change",
    "partial_update": "change",
    "destroy": "delete",
}


def model_permissions(action, app_label, model, default="view"):
    """The permission classes guarding one action on one model.

    Returns the standard trio: authenticated, inside the right tenant, and
    holding `app_label.<verb>_<model>` from the catalogue in authorization.rbac.
    Building the name here rather than at each call site means a viewset cannot
    quietly check a permission that no role grants.
    """
    verb = CRUD_ACTIONS.get(action, default)
    return [
        IsAuthenticated(),
        IsOrganizationUser(),
        HasUserPermission(f"{app_label}.{verb}_{model}"),
    ]

class HasUserPermission(BasePermission):
    """
    Custom permission to check if the user has a specific permission.
    """
    def __init__(self, perm_name):
        self.perm_name = perm_name

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_superuser_admin:
            return True
        return self.perm_name in self._permission_names(request)

    @staticmethod
    def _permission_names(request):
        """The caller's permissions, resolved once per request.

        A view may apply several of these checks, and each one used to walk the
        role assignments from scratch. Cached on the request rather than on the
        user so it cannot outlive the request that resolved it.
        """
        cached = getattr(request, '_permission_names_cache', None)
        if cached is None:
            cached = request.user.get_permission_names()
            request._permission_names_cache = cached
        return cached

class IsPlatformStaff(BasePermission):
    """Anyone who works for Blendy rather than for a shop.

    Deliberately "holds *any* platform permission" rather than a named one: this
    guards knowing that HQ exists and what its id is, which every platform role
    needs — a support agent has to send that id to manage their own account.
    Anything consequential is gated on a specific permission instead.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_superuser_admin:
            return True
        return any(
            name.startswith("platform.")
            for name in HasUserPermission._permission_names(request)
        )


class IsSuperAdminUser(BasePermission):
    """
    Allows access only to super admin users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser_admin)

class IsOrganizationUser(BasePermission):
    """Access to an organization's data.

    Three ways in, in order of how ordinary they are:

    1. **Membership** — the caller belongs to the organization named by the
       X-Organization header. This is every shop user, every request.
    2. **Platform staff** holding `platform.access_tenants` may read any
       organization, and additionally need `platform.act_as_tenant` to write.
       Their permissions resolve against HQ's roles, so what they can see once
       across the boundary is still decided by the ordinary per-model checks.
    3. **`is_superuser_admin`** — the break-glass flag, kept as an unconditional
       bypass in the spirit of Django's own `is_superuser`.

    Crossing the boundary by route 2 or 3 is recorded by
    organization.middleware.PlatformAccessLogMiddleware. That logging is
    deliberately not done here: a view that forgets to apply this class would
    otherwise slip through unlogged.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        organization = getattr(request, "organization", None)
        if organization is None:
            # Fail closed. Without a named tenant there is nothing to authorise
            # against, and "no tenant" must never mean "every tenant".
            return False

        if request.user.organization_id == organization.id:
            return True

        return self._may_cross_tenants(request)

    @staticmethod
    def _may_cross_tenants(request):
        """Whether this caller may reach an organization they are not in."""
        user = request.user
        if user.is_superuser or user.is_superuser_admin:
            return True

        held = HasUserPermission._permission_names(request)
        if "platform.access_tenants" not in held:
            return False

        if request.method in SAFE_METHODS:
            return True

        # Writing into someone else's shop is a second, separate grant, so a
        # support role can look without being able to touch.
        return "platform.act_as_tenant" in held

class IsOrgAdmin(IsOrganizationUser):
    """
    Allows access only to ORG_ADMIN users within their organization.
    """
    def has_permission(self, request, view):
        # Check if the user is an organization admin (based on the is_organization_admin flag)
        return super().has_permission(request, view) and request.user.is_organization_admin

class IsSuperAdminOrOrgAdmin(BasePermission):
    """Someone who administers people: a shop's admin, or Blendy's.

    Says nothing about *which* organization — pair it with IsOrganizationUser,
    which is what decides that. On its own it would let the admin of one shop
    administer another simply by changing the X-Organization header.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser_admin or request.user.is_organization_admin:
            return True
        # Blendy staff who manage accounts hold this instead of the flag, so it
        # can be granted and revoked per person.
        return "platform.manage_platform_staff" in HasUserPermission._permission_names(
            request
        )