from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LocationViewSet, 
    InventoryItemViewSet, StockMovementViewSet, 
    StockTakeViewSet, StockTakeItemViewSet, AgentInventoryItemViewSet
)

router = DefaultRouter()
router.register(r'locations', LocationViewSet)
router.register(r'inventory-items', InventoryItemViewSet)
router.register(r'stock-movements', StockMovementViewSet)
router.register(r'stock-takes', StockTakeViewSet)
router.register(r'stock-take-items', StockTakeItemViewSet)
router.register(r'agent-inventory', AgentInventoryItemViewSet, basename='agent-inventory-item')

urlpatterns = [
    path('', include(router.urls)),
]