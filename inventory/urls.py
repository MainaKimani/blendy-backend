from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LocationViewSet,
    InventoryItemViewSet, StockMovementViewSet,
    StockTakeViewSet, StockTakeItemViewSet,
    RestockView, StockAdjustmentView, LowStockListView
)

router = DefaultRouter()
router.register(r'locations', LocationViewSet)
router.register(r'inventory-items', InventoryItemViewSet)
router.register(r'stock-movements', StockMovementViewSet)
router.register(r'stock-takes', StockTakeViewSet)
router.register(r'stock-take-items', StockTakeItemViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # The write path for stock. The ledger viewset above is read-only.
    path('stock/restock/', RestockView.as_view(), name='stock-restock'),
    path('stock/adjust/', StockAdjustmentView.as_view(), name='stock-adjust'),
    path('stock/low-stock/', LowStockListView.as_view(), name='stock-low-stock'),
]