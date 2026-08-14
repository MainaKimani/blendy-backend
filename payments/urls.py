from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    MpesaC2BConfirmationView,
    MpesaWebhookView,
    PaymentViewSet,
    RefundViewSet,
)

router = DefaultRouter()
router.register(r"payments", PaymentViewSet)
router.register(r"refunds", RefundViewSet)

urlpatterns = [
    path("", include(router.urls)),
    # The token segment authenticates the caller: Safaricom does not sign
    # callbacks, so the URL itself has to be the shared secret. It must match
    # MPESA_WEBHOOK_TOKEN and the callback URL registered with Daraja.
    path(
        "webhooks/mpesa/<str:token>/",
        MpesaWebhookView.as_view(),
        name="mpesa-webhook",
    ),
    # C2B confirmation URL for direct Till payments. Registered separately with
    # Daraja from the STK callback above.
    path(
        "webhooks/mpesa-c2b/<str:token>/",
        MpesaC2BConfirmationView.as_view(),
        name="mpesa-c2b-confirmation",
    ),
]
