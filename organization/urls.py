from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrganizationViewSet, OnboardOrganizationView

router = DefaultRouter()
router.register(r'', OrganizationViewSet, basename='organization')

urlpatterns = [
    path('onboard/', OnboardOrganizationView.as_view(), name='onboard-organization'),
    path('', include(router.urls)),
]
