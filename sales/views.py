from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Sale, SaleItem
from .serializers import SaleSerializer, SaleItemSerializer
from inventory.views import OrganizationBaseViewSet
from users.permissions import IsOrganizationUser, model_permissions


class SaleViewSet(OrganizationBaseViewSet):
    # Everything the serializer walks is pulled in up front. `items` serves both
    # the nested lines and the total_amount property from one cache, and the
    # variation is prefetched because each line exposes its parent product.
    queryset = Sale.objects.prefetch_related(
        "items__product_variation", "payments__transactions"
    )
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
        # Guest checkout: creating a sale stays open to anonymous callers, and
        # is deliberately *not* permission-gated — a customer paying at the till
        # holds no role. Everything that reads or mutates an existing sale is.
        # `pending-payments` is not a CRUD action, so it falls through to the
        # read verb and needs sales.view_sale.
        if self.action == "create":
            return [AllowAny()]
        return model_permissions(self.action, "sales", "sale")

    @swagger_auto_schema(
        operation_summary="Sales still waiting on money",
        operation_description=(
            "Sales whose payment_status is AWAITING_DIRECT_PAYMENT — an STK push "
            "failed and the customer was asked to pay the Till directly — or "
            "UNPAID. The owner's queue for anything that would otherwise sit "
            "unnoticed (US-10)."
        ),
        responses={200: SaleSerializer(many=True)},
    )
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

    # Each line exposes its parent product, which is reached through the
    # variation, so the variation is joined rather than fetched per row.
    queryset = SaleItem.objects.select_related("product_variation")
    serializer_class = SaleItemSerializer

    def get_permissions(self):
        return model_permissions(self.action, "sales", "saleitem")
