from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Sale, SaleItem
from .serializers import SaleSerializer, SaleItemSerializer
from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser


class SaleViewSet(OrganizationBaseViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer

    def perform_create(self, serializer):
        # Guest checkout is supported, so created_by stays null for anonymous
        # callers; the tenant comes from the X-Organization header either way.
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to record a sale."
            )
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(organization=organization, created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_permissions(self):
        # Allow guests to POST (checkout), but require auth to read or mutate
        # existing sales.
        if self.action == "create":
            return [AllowAny()]
        return [IsAuthenticated(), IsOrganizationUser()]

    @action(detail=False, methods=["get"], url_path="pending-payments")
    def pending_payments(self, request):
        """Sales still waiting on money (US-10).

        Covers sales awaiting a direct Till payment after a failed STK push, as
        well as ones never paid at all, so nothing sits unnoticed.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(
            payment_status__in=["AWAITING_DIRECT_PAYMENT", "UNPAID"]
        )
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(
            page if page is not None else queryset, many=True
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class SaleItemViewSet(OrganizationBaseViewSet):

    queryset = SaleItem.objects.all()
    serializer_class = SaleItemSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]
