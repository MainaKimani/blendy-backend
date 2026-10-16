from authentication import serializers
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import CustomUser
from .serializers import CustomUserSerializer
from authorization.models import Role, OrganizationRole, UserRoleAssignment
from authorization.rbac import VIEWER
from django.db import transaction
from users.permissions import IsOrganizationUser, IsSuperAdminOrOrgAdmin, HasUserPermission


class CustomUserViewSet(viewsets.ModelViewSet):
    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated, IsOrganizationUser]

    def get_permissions(self):
        # IsOrganizationUser on *every* action, not only update. Without it the
        # admin of one shop could create and list users inside another simply by
        # changing the X-Organization header, because the queryset and
        # perform_create both take the organization from that header while
        # nothing checked the caller belonged to it.
        #
        # It is also what lets Blendy staff manage a shop's users while acting
        # as that shop, since IsOrganizationUser now understands platform
        # access, and what confines HQ staff management to HQ.
        return [
            IsAuthenticated(),
            IsOrganizationUser(),
            IsSuperAdminOrOrgAdmin(),
        ]

    def get_queryset(self):
        return CustomUser.objects.filter(organization=self.request.organization)

    def perform_create(self, serializer):
        # Ensure the user is created within the correct organization
        organization = self.request.organization
        user = serializer.save(organization=organization)

        # Handle role assignments
        organization_role_ids = self.request.data.get("organization_role_ids", [])
        if organization_role_ids:
            with transaction.atomic():
                # Clear existing assignments for the user within their organization
                UserRoleAssignment.objects.filter(
                    user=user, organization_role__organization=organization
                ).delete()

                for org_role_id in organization_role_ids:
                    try:
                        org_role = OrganizationRole.objects.get(
                            id=org_role_id, organization=organization
                        )
                        UserRoleAssignment.objects.create(
                            user=user, organization_role=org_role
                        )
                    except OrganizationRole.DoesNotExist:
                        raise serializers.ValidationError(
                            f"Organization role with ID {org_role_id} not found or not valid for this organization."
                        )

    def perform_update(self, serializer):
        # Ensure the user is updated within the correct organization
        organization = self.request.organization
        user = serializer.save(organization=organization)

        # Handle role assignments
        organization_role_ids = self.request.data.get("organization_role_ids", None)
        if organization_role_ids is not None:
            with transaction.atomic():
                # Clear existing assignments for the user within their organization
                UserRoleAssignment.objects.filter(
                    user=user, organization_role__organization=organization
                ).delete()

                for org_role_id in organization_role_ids:
                    try:
                        org_role = OrganizationRole.objects.get(
                            id=org_role_id, organization=organization
                        )
                        UserRoleAssignment.objects.create(
                            user=user, organization_role=org_role
                        )
                    except OrganizationRole.DoesNotExist:
                        raise serializers.ValidationError(
                            f"Organization role with ID {org_role_id} not found or not valid for this organization."
                        )


class MeView(APIView):
    """Who the caller is and what they may do.

    A client needs this to decide which screens to offer. Nothing else answers
    it for an ordinary user: login returns only ids, and `/api/users/{id}/` is
    admin-only, so a cashier could not read their own roles.

    Resolved against the caller's *own* organization, never the X-Organization
    header — platform staff browsing a shop still hold only their HQ
    permissions, and that is what the client must render against.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        organization = user.organization
        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "organization": (
                    {
                        "id": str(organization.id),
                        "name": organization.name,
                        "slug": organization.slug,
                        "is_platform": organization.is_platform,
                    }
                    if organization
                    else None
                ),
                "roles": sorted(
                    user.role_assignments.filter(
                        organization_role__organization_id=user.organization_id
                    ).values_list("organization_role__role__name", flat=True)
                ),
                "permissions": sorted(user.get_permission_names()),
                # Superadmins bypass every permission check, so a client cannot
                # infer their access from the permission list alone.
                "is_superuser_admin": bool(
                    user.is_superuser or user.is_superuser_admin
                ),
            }
        )


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = CustomUserSerializer(data=request.data)
        if serializer.is_valid():
            organization = getattr(request, "organization", None)
            if not organization:
                return Response(
                    {
                        "detail": "Organization not found. Please provide X-Organization header."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = serializer.save(organization=organization)

            # Give the new account the VIEWER role, which is seeded by
            # authorization.rbac and enabled for every organization.
            #
            # This looked up the literal name "Viewer" and swallowed
            # Role.DoesNotExist, so for as long as nothing seeded roles it
            # silently assigned nothing and every self-registered user ended up
            # with no role at all. Referencing the constant means a rename in
            # the catalogue cannot quietly break it again.
            #
            # VIEWER is scoped for this path specifically: registration is open
            # to anonymous callers and needs only an organization id, so the
            # role holds catalogue reads and nothing else.
            viewer_role = Role.objects.filter(name=VIEWER).first()
            if viewer_role is not None:
                org_role, _ = OrganizationRole.objects.get_or_create(
                    organization=organization, role=viewer_role
                )
                UserRoleAssignment.objects.get_or_create(
                    user=user, organization_role=org_role
                )

            return Response(
                CustomUserSerializer(user).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
