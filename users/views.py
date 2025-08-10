from authentication import serializers
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import CustomUser
from .serializers import CustomUserSerializer
from authorization.models import Role, OrganizationRole, UserRoleAssignment
from django.db import transaction
from users.permissions import IsOrganizationUser, IsSuperAdminOrOrgAdmin, HasUserPermission


class CustomUserViewSet(viewsets.ModelViewSet):
    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated, IsOrganizationUser]

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [IsAuthenticated(), IsSuperAdminOrOrgAdmin(),]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsSuperAdminOrOrgAdmin(),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsSuperAdminOrOrgAdmin(),
                IsOrganizationUser()
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsSuperAdminOrOrgAdmin(),
            ]
        return [IsAuthenticated(), IsSuperAdminOrOrgAdmin()]

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

            # Assign a default role (e.g., 'Viewer') to newly registered users
            # You would need to ensure a 'Viewer' role exists globally and is linked to the organization
            try:
                default_role = Role.objects.get(
                    name="Viewer"
                )  # Assuming a global 'Viewer' role exists
                org_role, created = OrganizationRole.objects.get_or_create(
                    organization=organization, role=default_role
                )
                UserRoleAssignment.objects.create(user=user, organization_role=org_role)
            except Role.DoesNotExist:
                # Handle case where default role doesn't exist
                pass  # Or raise an error, depending on your policy

            return Response(
                CustomUserSerializer(user).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
