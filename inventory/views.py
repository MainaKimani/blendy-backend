from django.db.models import F
from drf_yasg.utils import swagger_auto_schema
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from users.permissions import (
    IsOrganizationUser, HasUserPermission, model_permissions
)
from .models import (
    Location, InventoryItem,
    StockMovement, StockTake, StockTakeItem
)
from .serializers import (
    LocationSerializer,
    InventoryItemSerializer, StockMovementSerializer,
    StockTakeSerializer, StockTakeItemSerializer,
    RestockSerializer, StockAdjustmentSerializer, LowStockItemSerializer,
    StockWriteResponseSerializer
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

    def get_permissions(self):
        return model_permissions(self.action, "inventory", "location")

class InventoryItemViewSet(OrganizationBaseViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer

    def get_permissions(self):
        return model_permissions(self.action, "inventory", "inventoryitem")

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

    def get_permissions(self):
        return model_permissions(self.action, "inventory", "stockmovement")

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
        return [
            IsAuthenticated(),
            IsOrganizationUser(),
            HasUserPermission("inventory.view_lowstock"),
        ]

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
            # `name` is a property that reads product.name *and* uom.symbol,
            # so both are joined. Omitting uom cost a query per row for any
            # organization that actually records units of measure.
            .select_related(
                "product_variation__product", "product_variation__uom", "location"
            )
            # Most urgent first, with a tiebreak so pagination is stable.
            .order_by("available_quantity", "product_variation_id")
        )


class BaseStockWriteView(APIView):
    """Shared plumbing for the endpoints that move stock."""

    # Named on each subclass. Moving stock is not plain CRUD on a
    # StockMovement row — the ledger is append-only and written only here — so
    # it has its own permission rather than borrowing `add_stockmovement`.
    stock_permission = None

    def get_permissions(self):
        # Moving stock is never anonymous: every ledger entry is attributed.
        return [
            IsAuthenticated(),
            IsOrganizationUser(),
            HasUserPermission(self.stock_permission),
        ]

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

    stock_permission = "inventory.restock_stock"

    @swagger_auto_schema(
        operation_summary="Record stock arriving",
        operation_description=(
            "Adds stock through the ledger. `quantity` is always positive here; "
            "use the adjust endpoint to remove or correct stock. `unit_cost` is "
            "optional and recorded against the movement for later margin "
            "reporting. Omitting `location` uses the organization's default."
        ),
        request_body=RestockSerializer,
        responses={
            201: StockWriteResponseSerializer,
            400: "Validation error.",
            403: "Missing X-Organization header, or the variation belongs to another organization.",
        },
    )
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

    stock_permission = "inventory.adjust_stock"

    @swagger_auto_schema(
        operation_summary="Correct a stock figure",
        operation_description=(
            "Send **exactly one** of:\n\n"
            "- `quantity` — a signed change, e.g. `-2` for two broken units. "
            "Cannot take the balance below zero.\n"
            "- `counted_quantity` — the figure counted on the shelf. The "
            "difference is computed under the row lock that writes it, and a "
            "count is authoritative, so it may produce a negative balance.\n\n"
            "`reason` is required either way: an unexplained adjustment is what "
            "the ledger exists to rule out."
        ),
        request_body=StockAdjustmentSerializer,
        responses={
            201: StockWriteResponseSerializer,
            200: "The counted figure already matched; nothing was written.",
            400: "Validation error, or a delta that would take stock below zero.",
            403: "Missing X-Organization header, or a cross-tenant reference.",
        },
    )
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

    def get_permissions(self):
        return model_permissions(self.action, "inventory", "stocktake")

class StockTakeItemViewSet(OrganizationBaseViewSet):
    queryset = StockTakeItem.objects.all()
    serializer_class = StockTakeItemSerializer

    def get_permissions(self):
        return model_permissions(self.action, "inventory", "stocktakeitem")

