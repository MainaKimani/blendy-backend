from django.db import transaction
from django.db.models import Min
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from pricing.services import (
    PricelistUnavailable,
    require_default_pricelist,
    set_price,
)
from users.permissions import IsOrganizationUser, HasUserPermission
from .models import Product, ProductImage, Category, ProductVariation, Currency, UOM
from .serializers import (
    ProductSerializer,
    CategorySerializer,
    ProductImageSerializer,
    ProductImageWritableSerializer,
    ProductVariationWriteSerializer,
    ProductVariationSerializer,
    ProductWithPriceSerializer,
    CurrencySerializer,
    UOMSerializer,
)
from inventory.views import OrganizationBaseViewSet
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from .filters import ProductFilter


class CategoryViewSet(OrganizationBaseViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                # IsAuthenticated(),
                # IsOrganizationUser(),
                # HasUserPermission("products.view_category"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.add_category"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.change_category"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.delete_category"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


class ProductViewSet(OrganizationBaseViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    # Add the backends here
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    # Use the custom FilterSet class instead of the simple list
    filterset_class = ProductFilter

    # Search is still handled by DRF's SearchFilter
    search_fields = ["name", "is_active", "sku", "tags"]

    # Optional: Allow users to sort the results (e.g., /?ordering=-price)
    ordering_fields = ["price", "created_at"]

    ordering = ["-created_at"]

    def get_queryset(self):
        # Product no longer holds a price, so ordering by it is served from the
        # cheapest priced variation on any of the organization's pricelists.
        #
        # Everything the serializer reads is pulled in here. Without it each
        # product cost a query for its category, its images, its variations, and
        # then three more per variation for uom, currency and pricelist price —
        # 243 queries for 20 products. With it, the listing is a flat 6.
        return (
            super()
            .get_queryset()
            .select_related("category")
            .prefetch_related(
                "images",
                "variations__uom",
                "variations__currency",
                "variations__pricelist_items",
            )
            .annotate(price=Min("variations__pricelist_items__price"))
        )

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                # IsAuthenticated(),
                # IsOrganizationUser(),
                # HasUserPermission("products.view_product"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.add_product"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.change_product"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.delete_product"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


class ProductVariationViewSet(OrganizationBaseViewSet):
    queryset = ProductVariation.objects.all()

    # default (read)
    serializer_class = ProductVariationSerializer

    # Use different serializers for read vs write
    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductVariationWriteSerializer
        return ProductVariationSerializer

    # Clean permissions (less repetition)
    def get_permissions(self):
        base_permissions = [IsAuthenticated(), IsOrganizationUser()]

        permission_map = {
            "list": base_permissions,
            "retrieve": base_permissions,
            "create": base_permissions,
            "update": base_permissions,
            "partial_update": base_permissions,
            "destroy": base_permissions,
        }

        return permission_map.get(self.action, base_permissions)

    # Scope queryset by organization (VERY IMPORTANT in multi-tenant)
    def get_queryset(self):
        # `name` is a property that reads product.name and uom.symbol, and the
        # price comes off the pricelist, so all three are pulled in here rather
        # than fetched per row.
        return (
            super()
            .get_queryset()
            .filter(organization=self.request.user.organization)
            .select_related("product", "uom", "currency")
            .prefetch_related("pricelist_items")
        )

    # Bulk + single create support
    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)

        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Inject organization automatically, and record each price on the pricelist
    @transaction.atomic
    def perform_create(self, serializer):
        organization = self.request.user.organization
        try:
            pricelist = require_default_pricelist(organization)
        except PricelistUnavailable as exc:
            raise ValidationError({"selling_price": str(exc)})

        payload = serializer.validated_data
        rows = payload if isinstance(payload, list) else [payload]

        created = []
        for item in rows:
            # The selling price belongs on the pricelist, not the variation.
            selling_price = item.pop("selling_price")
            variation = ProductVariation.objects.create(
                organization=organization, **item
            )
            set_price(
                organization=organization,
                pricelist=pricelist,
                product_variation=variation,
                price=selling_price,
            )
            created.append(variation)

        serializer.instance = created if isinstance(payload, list) else created[0]

    # def get_permissions(self):
    #     if self.action == "list" or self.action == "retrieve":
    #         return [
    #             IsAuthenticated(),
    #             IsOrganizationUser(),
    #             #HasUserPermission("products.view_productvariation"),
    #         ]
    #     elif self.action == "create":
    #         return [
    #             IsAuthenticated(),
    #             IsOrganizationUser(),
    #             #HasUserPermission("products.add_productvariation"),
    #         ]
    #     elif self.action == "update" or self.action == "partial_update":
    #         return [
    #             IsAuthenticated(),
    #             IsOrganizationUser(),
    #             #HasUserPermission("products.change_productvariation"),
    #         ]
    #     elif self.action == "destroy":
    #         return [
    #             IsAuthenticated(),
    #             IsOrganizationUser(),
    #             #HasUserPermission("products.delete_productvariation"),
    #         ]
    #     return [IsAuthenticated(), IsOrganizationUser()]


class ProductImageViewSet(OrganizationBaseViewSet):
    queryset = ProductImage.objects.all()
    # default (read)
    serializer_class = ProductImageSerializer

    # Use different serializers for read vs write
    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return ProductImageWritableSerializer
        return ProductImageSerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return []
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.add_product"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.change_product"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                # HasUserPermission("products.delete_product"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


class ProductWithPriceViewSet(OrganizationBaseViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductWithPriceSerializer

    def get_queryset(self):
        # Same serializer shape as ProductViewSet, so the same prefetches apply.
        return (
            super()
            .get_queryset()
            .select_related("category")
            .prefetch_related(
                "images",
                "variations__uom",
                "variations__currency",
                "variations__pricelist_items",
            )
        )

    def get_permissions(self):
        return []


class CurrencyViewSet(OrganizationBaseViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]


class UOMViewSet(OrganizationBaseViewSet):
    queryset = UOM.objects.all()
    serializer_class = UOMSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsOrganizationUser()]
