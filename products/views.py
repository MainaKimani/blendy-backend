from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsOrganizationUser, HasUserPermission
from .models import Product, Category, ProductVariation, Currency, UOM
from .serializers import (
    ProductSerializer,
    CategorySerializer,
    ProductVariationWriteSerializer,
    ProductVariationSerializer,
    ProductWithPriceSerializer,
    CurrencySerializer,
    UOMSerializer,
)
from inventory.views import OrganizationBaseViewSet


class CategoryViewSet(OrganizationBaseViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                # IsAuthenticated(),
                # IsOrganizationUser(),
                #HasUserPermission("products.view_category"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.add_category"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.change_category"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.delete_category"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


class ProductViewSet(OrganizationBaseViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                # IsAuthenticated(),
                # IsOrganizationUser(),
                #HasUserPermission("products.view_product"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.add_product"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.change_product"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.delete_product"),
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
        return super().get_queryset().filter(
            organization=self.request.user.organization
        )

    # Bulk + single create support
    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)

        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)

        self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # Inject organization automatically
    def perform_create(self, serializer):
        if isinstance(serializer.validated_data, list):
            # bulk create
            instances = [
                ProductVariation(organization=self.request.user.organization, **item)
                for item in serializer.validated_data
            ]
            ProductVariation.objects.bulk_create(instances)
        else:
            serializer.save(organization=self.request.user.organization)

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


class ProductWithPriceViewSet(OrganizationBaseViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductWithPriceSerializer

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
