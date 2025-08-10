from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsOrganizationUser, HasUserPermission
from .models import (
    Location, InventoryItem, 
    StockMovement, StockTake, StockTakeItem, AgentInventoryItem
)
from .serializers import (
    LocationSerializer, 
    InventoryItemSerializer, StockMovementSerializer, 
    StockTakeSerializer, StockTakeItemSerializer, AgentInventoryItemSerializer
)
from products.models import Product
from users.models import CustomUser

class OrganizationBaseViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        return []

    def get_queryset(self):
        queryset = self.queryset
        if hasattr(self.request, 'organization') and self.request.organization:
            queryset = queryset.filter(organization=self.request.organization)
        return queryset

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

class LocationViewSet(OrganizationBaseViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer

class InventoryItemViewSet(OrganizationBaseViewSet):
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer

class StockMovementViewSet(OrganizationBaseViewSet):
    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer

class StockTakeViewSet(OrganizationBaseViewSet):
    queryset = StockTake.objects.all()
    serializer_class = StockTakeSerializer

class StockTakeItemViewSet(OrganizationBaseViewSet):
    queryset = StockTakeItem.objects.all()
    serializer_class = StockTakeItemSerializer

class AgentInventoryItemViewSet(OrganizationBaseViewSet):
    """
    A viewset for viewing and managing the inventory held by sales agents.
    """
    queryset = AgentInventoryItem.objects.all()
    serializer_class = AgentInventoryItemSerializer

    def get_permissions(self):
        if self.action == 'list' or self.action == 'retrieve':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('inventory.view_agentinventoryitem')]
        elif self.action == 'create':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('inventory.add_agentinventoryitem')]
        elif self.action == 'update' or self.action == 'partial_update':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('inventory.change_agentinventoryitem')]
        elif self.action == 'destroy':
            return [IsAuthenticated(), IsOrganizationUser(), HasUserPermission('inventory.delete_agentinventoryitem')]
        return [IsAuthenticated(), IsOrganizationUser()]

    def get_queryset(self):
        """
        Optionally restricts the returned purchases to a given user,
        by filtering against a `username` query parameter in the URL.
        """
        queryset = super().get_queryset()
        agent_id = self.request.query_params.get('agent_id')
        if agent_id is not None:
            queryset = queryset.filter(agent__id=agent_id)
        return queryset
