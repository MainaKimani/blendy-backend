from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, CategoryViewSet, ProductVariationViewSet, ProductWithPriceViewSet, CurrencyViewSet, UOMViewSet

router = DefaultRouter()
router.register(r'with-price', ProductWithPriceViewSet, basename='product-with-price')
router.register(r'variations', ProductVariationViewSet, basename='product-variation')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'uoms', UOMViewSet, basename='uom')
router.register(r'', ProductViewSet, basename='product')

urlpatterns = [
    path('', include(router.urls)),
]
