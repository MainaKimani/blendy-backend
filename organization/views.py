from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Organization, PlatformAccessLog
from .serializers import (
    OrganizationSerializer,
    OnboardOrganizationSerializer,
    PlatformAccessLogSerializer,
    TenantAccessLogSerializer,
)
from rest_framework.decorators import action

from organization.services import get_platform_organization
from users.permissions import (
    HasUserPermission,
    IsOrganizationUser,
    IsPlatformStaff,
    IsSuperAdminUser,
    IsOrgAdmin,
    IsOrganizationUser,
    HasUserPermission,
    IsSuperAdminOrOrgAdmin,
)
from users.serializers import CustomUserSerializer
from organization.services import tenants
from pricing.services import create_default_pricelist


class OnboardOrganizationView(APIView):
    """
    Creates a new Organization and its primary ORG_ADMIN user.
    Only accessible by users with the SUPER_ADMIN role.
    """

    def get_permissions(self):
        # Was IsSuperAdminUser, i.e. the flag and nothing else. Now a
        # permission, so a PLATFORM_ADMIN can onboard shops without being
        # handed break-glass access to everything. HasUserPermission
        # short-circuits for superadmins, so the flag still works.
        return [
            IsAuthenticated(),
            HasUserPermission("platform.onboard_organization"),
        ]

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
    """Customer organizations.

    HQ is excluded: it is an Organization for RBAC's sake, not a tenant, and
    listing it here would put Blendy in its own customer list — and later, in
    its own billing run.
    """

    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        return tenants()

    @swagger_auto_schema(
        operation_summary="The platform (HQ) organization",
        operation_description=(
            "Blendy's own organization, which the customer listing deliberately "
            "excludes. Platform staff need its id to send as X-Organization "
            "when working on HQ itself — managing their own staff, for "
            "instance — and it is otherwise only obtainable from the shell.\n\n"
            "Open to any holder of a `platform.*` permission, since knowing HQ "
            "exists is not itself sensitive."
        ),
        responses={
            200: OrganizationSerializer,
            403: "Not platform staff.",
            404: "No platform organization exists; run `manage.py bootstrap_hq`.",
        },
    )
    @action(detail=False, methods=["get"], permission_classes=[])
    def platform(self, request):
        organization = get_platform_organization()
        if organization is None:
            return Response(
                {
                    "detail": (
                        "No platform organization exists. "
                        "Run `manage.py bootstrap_hq`."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrganizationSerializer(organization).data)

    def perform_create(self, serializer):
        # An organization created here needs a pricelist just as much as one
        # created through onboarding, or it cannot sell anything.
        organization = serializer.save()
        create_default_pricelist(organization)

    def get_permissions(self):
        if self.action == "platform":
            # Not IsSuperAdminUser: a support agent needs HQ's id too, and
            # gating it on the flag would send them back to the shell.
            return [IsAuthenticated(), IsPlatformStaff()]
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


class PlatformAccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Who reached into which organization, and whether they were allowed.

    Read-only by construction: an audit trail that its subject — or its actor —
    can edit is not one. There is no write path at all, not even for a
    superadmin, so the only way a row changes is a database migration.

    Not tenant-scoped. It records access *across* tenants, so scoping it to one
    would hide exactly the rows worth looking at.
    """

    queryset = PlatformAccessLog.objects.select_related("actor", "organization")
    serializer_class = PlatformAccessLogSerializer
    filterset_fields = ["organization", "actor", "granted", "method"]

    def get_permissions(self):
        # Held only by PLATFORM_ADMIN. A shop's ORG_ADMIN holds all 87 tenant
        # permissions and still not this one.
        return [IsAuthenticated(), HasUserPermission("platform.view_access_log")]


class OrganizationAccessLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Who outside this organization has reached into its data.

    The tenant-facing half of the audit trail. A shop whose revenue figures
    Blendy staff can read should be able to see when that happened, without
    asking us — an assurance that is worth little if it depends on us answering.

    Scoped to the caller's own organization and read-only, like its HQ
    counterpart. Where the two differ is *who gets named*: see
    TenantAccessLogSerializer.
    """

    queryset = PlatformAccessLog.objects.all()
    serializer_class = TenantAccessLogSerializer
    filterset_fields = ["granted", "method", "actor_is_platform"]

    def get_permissions(self):
        # A tenant permission, so ORG_ADMIN holds it by derivation. A cashier
        # does not: who has been looking at the shop's books is the owner's
        # business.
        return [
            IsAuthenticated(),
            IsOrganizationUser(),
            HasUserPermission("organization.view_access_log"),
        ]

    def get_queryset(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            # Fail closed, as everywhere else: no tenant means no rows.
            return PlatformAccessLog.objects.none()
        return PlatformAccessLog.objects.filter(organization=organization)
