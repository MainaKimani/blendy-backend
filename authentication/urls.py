from django.urls import path, include
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView
from .views import (
    UserSessionViewSet,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    PasswordChangeView,
    LogoutView,
)

router = DefaultRouter()
router.register(r'sessions', UserSessionViewSet, basename='user-session')

urlpatterns = [
    path("", include(router.urls)),
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("password-change/", PasswordChangeView.as_view(), name="password_change"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
