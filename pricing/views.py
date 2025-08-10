from rest_framework import viewsets
from .models import Pricelist, PricelistItem
from .serializers import PricelistSerializer, PricelistItemSerializer
from inventory.views import OrganizationBaseViewSet
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsOrganizationUser, HasUserPermission

class PricelistViewSet(OrganizationBaseViewSet):
    queryset = Pricelist.objects.all()
    serializer_class = PricelistSerializer

    def get_permissions(self):
        if self.action == 'list' or self.action == 'retrieve':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.view_pricelist')]
        elif self.action == 'create':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.add_pricelist')]
        elif self.action == 'update' or self.action == 'partial_update':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.change_pricelist')]
        elif self.action == 'destroy':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.delete_pricelist')]
        return [IsAuthenticated(), IsOrganizationUser()]

class PricelistItemViewSet(viewsets.ModelViewSet):
    queryset = PricelistItem.objects.all()
    serializer_class = PricelistItemSerializer

    def get_permissions(self):
        if self.action == 'list' or self.action == 'retrieve':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.view_pricelistitem')]
        elif self.action == 'create':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.add_pricelistitem')]
        elif self.action == 'update' or self.action == 'partial_update':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.change_pricelistitem')]
        elif self.action == 'destroy':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('pricing.delete_pricelistitem')]
        return [IsAuthenticated(), IsOrganizationUser()]
