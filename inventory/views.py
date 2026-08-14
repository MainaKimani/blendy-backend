from django.db.models import F
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from users.permissions import IsOrganizationUser, HasUserPermission
from .models import (
    Location, InventoryItem,
    StockMovement, StockTake, StockTakeItem
)
from .serializers import (
    LocationSerializer,
    InventoryItemSerializer, StockMovementSerializer,
    StockTakeSerializer, StockTakeItemSerializer,
    RestockSerializer, StockAdjustmentSerializer, LowStockItemSerializer
)
from .services import (
    InsufficientStock, ledger_balance, record_movement, set_stock_level
)
from products.models import Product
from users.models import CustomUser

class OrganizationBaseViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        return []

    def get_tenant(self):
        """Resolve the caller's tenant, or None if the request carries no tenant.

        Tenancy comes from the X-Organization header via OrganizationMiddleware.
        Callers must treat None as "no access", never as "all tenants".
        """
        return getattr(self.request, 'organization', None)

    def get_queryset(self):
        organization = self.get_tenant()
        if organization is None:
            # Fail closed: without a tenant there is no such thing as a
            # legitimate result set, so return nothing rather than every row.
            return self.queryset.none()
        return self.queryset.filter(organization=organization)

    def perform_create(self, serializer):
        organization = self.get_tenant()
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to create this resource."
            )
        serializer.save(organization=organization)

class LocationViewSet(OrganizationBaseViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

class InventoryItemViewSet(OrganizationBaseViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer

class StockMovementViewSet(OrganizationBaseViewSet):
    """Read-only view of the stock ledger.

    The ledger is append-only and must stay in step with the cached balance on
    InventoryItem, so entries are written only through inventory.services. Left
    writable, a POST here recorded a movement that changed no stock level, which
    is precisely the drift the ledger exists to rule out. Use the restock and
    adjust endpoints instead.
    """

    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer
    http_method_names = ["get", "head", "options"]

class LowStockListView(generics.ListAPIView):
    """US-3: variations at or below the reorder level their owner set.

    There is no push channel in this deployment (no mail backend, no worker), so
    the alert is a queue the owner's dashboard reads, in the same shape as the
    pending-payments and unmatched-payments queues.

    The threshold is inclusive: MVP test scenario 8 expects selling *down to*
    the threshold to fire the alert, not only going under it.
    """

    serializer_class = LowStockItemSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]

    def get_queryset(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            return InventoryItem.objects.none()

        return (
            InventoryItem.objects.filter(
                organization=organization,
                # No threshold set means nothing to be below.
                product_variation__reorder_level__isnull=False,
                available_quantity__lte=F("product_variation__reorder_level"),
            )
            .select_related("product_variation__product", "location")
            # Most urgent first, with a tiebreak so pagination is stable.
            .order_by("available_quantity", "product_variation_id")
        )


class BaseStockWriteView(APIView):
    """Shared plumbing for the endpoints that move stock."""

    def get_permissions(self):
        # Moving stock is never anonymous: every ledger entry is attributed.
        # Narrowing this to owner-only awaits the RBAC seeding work, since
        # HasUserPermission matches Permission rows nothing currently creates.
        return [IsAuthenticated(), IsOrganizationUser()]

    def get_tenant(self, request):
        organization = getattr(request, "organization", None)
        if organization is None:
            raise PermissionDenied(
                "A valid X-Organization header is required to move stock."
            )
        return organization

    def validated(self, serializer_class, request, organization):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        variation = data["product_variation"]
        if variation.organization_id != organization.id:
            raise PermissionDenied(
                "Product variation does not belong to this organization."
            )
        location = data.get("location")
        if location is not None and location.organization_id != organization.id:
            raise PermissionDenied("Location does not belong to this organization.")
        return data

    def stock_response(self, organization, variation, movement, status_code):
        return Response(
            {
                "movement": StockMovementSerializer(movement).data
                if movement is not None
                else None,
                "product_variation": str(variation.id),
                "available_quantity": ledger_balance(organization, variation),
            },
            status=status_code,
        )


class RestockView(BaseStockWriteView):
    """US-17: record stock arriving, so low-stock alerts have somewhere to lead."""

    def post(self, request, *args, **kwargs):
        organization = self.get_tenant(request)
        data = self.validated(RestockSerializer, request, organization)

        movement = record_movement(
            organization=organization,
            product_variation=data["product_variation"],
            movement_type="STOCK_IN",
            quantity=data["quantity"],
            location=data.get("location"),
            user=request.user,
            unit_cost=data.get("unit_cost"),
            reference_number=data.get("reference_number", ""),
            notes=data.get("notes", ""),
        )
        return self.stock_response(
            organization, data["product_variation"], movement, status.HTTP_201_CREATED
        )


class StockAdjustmentView(BaseStockWriteView):
    """US-19: correct a stock figure, with the reason recorded against it."""

    def post(self, request, *args, **kwargs):
        organization = self.get_tenant(request)
        data = self.validated(StockAdjustmentSerializer, request, organization)
        variation = data["product_variation"]

        try:
            if data.get("counted_quantity") is not None:
                movement = set_stock_level(
                    organization=organization,
                    product_variation=variation,
                    counted_quantity=data["counted_quantity"],
                    location=data.get("location"),
                    user=request.user,
                    notes=data["reason"],
                )
            else:
                movement = record_movement(
                    organization=organization,
                    product_variation=variation,
                    movement_type="ADJUSTMENT",
                    quantity=data["quantity"],
                    location=data.get("location"),
                    user=request.user,
                    notes=data["reason"],
                )
        except InsufficientStock as exc:
            # A delta cannot take stock below zero; a physical count should be
            # recorded with counted_quantity instead.
            raise ValidationError({"quantity": str(exc)}) from exc

        # A count that matched changes nothing, which is a legitimate outcome.
        status_code = status.HTTP_201_CREATED if movement else status.HTTP_200_OK
        return self.stock_response(organization, variation, movement, status_code)


class StockTakeViewSet(OrganizationBaseViewSet):
    queryset = StockTake.objects.all()
    serializer_class = StockTakeSerializer

class StockTakeItemViewSet(OrganizationBaseViewSet):
    queryset = StockTakeItem.objects.all()
    serializer_class = StockTakeItemSerializer

