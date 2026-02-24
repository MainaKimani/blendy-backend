from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from .views import PricelistViewSet, PricelistItemViewSet

router = DefaultRouter()
router.register(r'pricelists', PricelistViewSet, basename='pricelist')
router.register(r'pricelist-items', PricelistItemViewSet, basename='pricelist-item')

urlpatterns = [
    path("", include(router.urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
