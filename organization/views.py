from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Organization
from .serializers import OrganizationSerializer, OnboardOrganizationSerializer
from users.permissions import (
    IsSuperAdminUser,
    IsOrgAdmin,
    IsOrganizationUser,
    HasUserPermission,
    IsSuperAdminOrOrgAdmin,
)
from users.serializers import CustomUserSerializer
from pricing.services import create_default_pricelist


class OnboardOrganizationView(APIView):
    """
    Creates a new Organization and its primary ORG_ADMIN user.
    Only accessible by users with the SUPER_ADMIN role.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    @swagger_auto_schema(
        operation_summary="Create an organization and its first admin",
        operation_description=(
            "Creates the organization, its `Default Pricelist` — without which "
            "it cannot price or sell anything — and its ORG_ADMIN user, in one "
            "transaction. The returned organization id is what callers then send "
            "as the `X-Organization` header."
        ),
        request_body=OnboardOrganizationSerializer,
        responses={
            201: openapi.Response(
                "Created.",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "organization": openapi.Schema(type=openapi.TYPE_OBJECT),
                        "user": openapi.Schema(type=openapi.TYPE_OBJECT),
                    },
                ),
            ),
            400: "Validation error.",
            403: "Caller is not a superadmin.",
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = OnboardOrganizationSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            # Return the created organization and user data
            response_data = {
                "organization": OrganizationSerializer(result["organization"]).data,
                "user": CustomUserSerializer(result["user"]).data,
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def perform_create(self, serializer):
        # An organization created here needs a pricelist just as much as one
        # created through onboarding, or it cannot sell anything.
        organization = serializer.save()
        create_default_pricelist(organization)

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                IsAuthenticated(),
                IsSuperAdminUser(),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsSuperAdminUser(),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsSuperAdminOrOrgAdmin(),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsSuperAdminOrOrgAdmin(),
            ]
        return [
            IsAuthenticated(),
            IsSuperAdminOrOrgAdmin(),
            IsOrganizationUser(),
        ]
