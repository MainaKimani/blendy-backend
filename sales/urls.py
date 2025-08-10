from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SalesAgentProfileViewSet, 
    IssueStockToAgentView,
    SaleViewSet,
    SaleItemViewSet
)

router = DefaultRouter()
router.register(r'profiles', SalesAgentProfileViewSet, basename='sales-agent-profile')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'sale-items', SaleItemViewSet, basename='sale-item')

urlpatterns = [
    path('', include(router.urls)),
    path('stock/issue-to-agent/', IssueStockToAgentView.as_view(), name='issue-stock-to-agent'),
]
