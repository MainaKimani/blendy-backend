from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PermissionViewSet, RoleViewSet, OrganizationRoleViewSet, UserRoleAssignmentViewSet

router = DefaultRouter()
router.register(r'permissions', PermissionViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'organization-roles', OrganizationRoleViewSet)
router.register(r'user-role-assignments', UserRoleAssignmentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
