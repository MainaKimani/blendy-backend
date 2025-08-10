from rest_framework.permissions import BasePermission
from rest_framework import permissions

class HasUserPermission(BasePermission):
    """
    Custom permission to check if the user has a specific permission.
    """
    def __init__(self, perm_name):
        self.perm_name = perm_name

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.has_perm(self.perm_name)

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