from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Permission, Role, OrganizationRole, UserRoleAssignment
from .serializers import PermissionSerializer, RoleSerializer, OrganizationRoleSerializer, UserRoleAssignmentSerializer
from users.permissions import IsSuperAdminUser, IsOrgAdmin, IsOrganizationUser
from inventory.views import OrganizationBaseViewSet # Reusing for organization-aware filtering

class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser] # Only SuperAdmin can manage global permissions

class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminUser] # Only SuperAdmin can manage global roles

class OrganizationRoleViewSet(OrganizationBaseViewSet):
    queryset = OrganizationRole.objects.all()
    serializer_class = OrganizationRoleSerializer
    # ORG_ADMINs can manage roles within their organization
    # SuperAdmins can also manage all organization roles
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsSuperAdminUser | IsOrgAdmin] # Need to define IsOrgAdmin
        else:
            self.permission_classes = [IsAuthenticated, IsOrganizationUser] # Any user in org can view
        return super().get_permissions()

class UserRoleAssignmentViewSet(OrganizationBaseViewSet):
    queryset = UserRoleAssignment.objects.all()
    serializer_class = UserRoleAssignmentSerializer
    # ORG_ADMINs can assign roles within their organization
    # SuperAdmins can also manage all user role assignments
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsSuperAdminUser | IsOrgAdmin] # Need to define IsOrgAdmin
        else:
            self.permission_classes = [IsAuthenticated, IsOrganizationUser] # Any user in org can view
        return super().get_permissions()
