from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, RefundViewSet

router = DefaultRouter()
router.register(r"payments", PaymentViewSet)
router.register(r"refunds", RefundViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
