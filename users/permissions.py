from rest_framework.permissions import BasePermission, IsAuthenticated
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

class IsSuperAdminUser(BasePermission):
    """
    Allows access only to super admin users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser_admin)

class IsOrganizationUser(BasePermission):
    """
    Allows access only to authenticated users belonging to the requested organization.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Ensure the user's organization matches the one from the X-Organization header
        return request.user.organization == request.organization

class IsOrgAdmin(IsOrganizationUser):
    """
    Allows access only to ORG_ADMIN users within their organization.
    """
    def has_permission(self, request, view):
        # Check if the user is an organization admin (based on the is_organization_admin flag)
        return super().has_permission(request, view) and request.user.is_organization_admin

class IsSuperAdminOrOrgAdmin(BasePermission):
    """
    Allows access to super admin users or organization admin users.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(request.user.is_superuser_admin or request.user.is_organization_admin)