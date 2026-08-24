from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OnboardOrganizationView,
    OrganizationAccessLogViewSet,
    OrganizationViewSet,
    PlatformAccessLogViewSet,
)

router = DefaultRouter()
# Registered before the catch-all '' route, or the empty prefix swallows it.
router.register(r'platform-access-log', PlatformAccessLogViewSet,
                basename='platform-access-log')
# What *this* organization can see about access to itself, as opposed to the
# HQ-wide view above.
router.register(r'access-log', OrganizationAccessLogViewSet,
                basename='access-log')
router.register(r'', OrganizationViewSet, basename='organization')

urlpatterns = [
    path('onboard/', OnboardOrganizationView.as_view(), name='onboard-organization'),
    path('', include(router.urls)),
]
