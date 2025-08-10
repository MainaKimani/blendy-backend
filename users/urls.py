from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomUserViewSet, RegisterView

router = DefaultRouter()
router.register(r'', CustomUserViewSet, basename='user')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('', include(router.urls)),
]
