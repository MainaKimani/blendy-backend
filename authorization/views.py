from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied, ValidationError
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
    """Which of the globally defined roles an organization has enabled.

    This is the only path that links a Role to an Organization. Onboarding
    creates the ORG_ADMIN link and registration creates the Viewer one, but
    every other role has to be enabled here — so unlike UserRoleAssignmentViewSet
    this one cannot simply be made read-only. Without a working create an owner
    could never turn on a role beyond those two, and the assignment flow on
    /api/users/ would have nothing to offer.
    """

    queryset = OrganizationRole.objects.all()
    serializer_class = OrganizationRoleSerializer

    def get_queryset(self):
        # The serializer nests the role, its permissions and the organization.
        return (
            super()
            .get_queryset()
            .select_related('role', 'organization')
            .prefetch_related('role__permissions')
            # No Meta.ordering on the model, and paginating an unordered
            # queryset can drop or repeat rows between pages.
            .order_by('-created_at', 'id')
        )

    def perform_create(self, serializer):
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                'A valid X-Organization header is required to enable a role.'
            )

        role = serializer.validated_data['role']
        if OrganizationRole.objects.filter(
            organization=organization, role=role
        ).exists():
            # organization is supplied here rather than by the client, so DRF
            # cannot build the UniqueTogetherValidator for it. Left unchecked, a
            # repeat request surfaced the database constraint as a 500.
            raise ValidationError(
                {'role_id': f"'{role.name}' is already enabled for this organization."}
            )

        serializer.save(organization=organization)

    # ORG_ADMINs can manage roles within their organization
    # SuperAdmins can also manage all organization roles
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsSuperAdminUser | IsOrgAdmin] # Need to define IsOrgAdmin
        else:
            self.permission_classes = [IsAuthenticated, IsOrganizationUser] # Any user in org can view
        return super().get_permissions()

class UserRoleAssignmentViewSet(OrganizationBaseViewSet):
    """Who holds which role, within one organization.

    UserRoleAssignment carries no organization column of its own: it is tenanted
    *transitively*, through organization_role. Inheriting the base scoping was
    therefore not merely wrong but inert — its get_queryset filtered on a field
    that does not exist, so every request raised FieldError before a single row
    was read, and the tenant isolation the base was assumed to be providing was
    never actually applied here.
    """

    queryset = UserRoleAssignment.objects.all()
    serializer_class = UserRoleAssignmentSerializer

    # Read-only. `user` and `organization_role` are both read-only on the
    # serializer, so a create had nothing to write and raised TypeError from an
    # empty UserRoleAssignment.objects.create(). Roles are assigned through
    # /api/users/ via organization_role_ids, which resolves the role inside the
    # caller's tenant first; there is no second write path to keep in step.
    http_method_names = ['get', 'head', 'options']

    def get_queryset(self):
        organization = self.get_tenant()
        if organization is None:
            # Fail closed, exactly as the base does: no tenant means no rows,
            # never every row.
            return self.queryset.none()

        return (
            self.queryset.filter(organization_role__organization=organization)
            # The serializer nests the role, its permissions, the organization,
            # and the user's own other assignments. Without these the listing
            # cost several queries per row.
            .select_related(
                'user',
                'organization_role__role',
                'organization_role__organization',
            )
            .prefetch_related(
                'organization_role__role__permissions',
                'user__role_assignments__organization_role__role',
            )
            # Assignments have no Meta.ordering, and paginating an unordered
            # queryset can drop or repeat rows between pages.
            .order_by('-assigned_at', 'id')
        )

    # ORG_ADMINs can assign roles within their organization
    # SuperAdmins can also manage all user role assignments
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated, IsSuperAdminUser | IsOrgAdmin] # Need to define IsOrgAdmin
        else:
            self.permission_classes = [IsAuthenticated, IsOrganizationUser] # Any user in org can view
        return super().get_permissions()
