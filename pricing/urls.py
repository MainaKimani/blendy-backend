from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PricelistViewSet, PricelistItemViewSet

router = DefaultRouter()
router.register(r'pricelists', PricelistViewSet, basename='pricelist')
router.register(r'pricelist-items', PricelistItemViewSet, basename='pricelist-item')

urlpatterns = [
    path('', include(router.urls)),
]
