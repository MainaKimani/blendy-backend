from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsOrganizationUser, HasUserPermission
from .models import Product, Category, ProductVariation, Currency, UOM
from .serializers import (
    ProductSerializer,
    CategorySerializer,
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
    serializer_class = ProductVariationSerializer

    def get_permissions(self):
        if self.action == "list" or self.action == "retrieve":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.view_productvariation"),
            ]
        elif self.action == "create":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.add_productvariation"),
            ]
        elif self.action == "update" or self.action == "partial_update":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.change_productvariation"),
            ]
        elif self.action == "destroy":
            return [
                IsAuthenticated(),
                IsOrganizationUser(),
                #HasUserPermission("products.delete_productvariation"),
            ]
        return [IsAuthenticated(), IsOrganizationUser()]


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
