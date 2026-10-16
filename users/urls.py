from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomUserViewSet, MeView, RegisterView

router = DefaultRouter()
router.register(r'', CustomUserViewSet, basename='user')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    # Before the router, whose detail route would otherwise read 'me' as an id.
    path('me/', MeView.as_view(), name='user-me'),
    path('', include(router.urls)),
]
