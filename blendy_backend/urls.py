"""
URL configuration for blendy_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from django.conf import settings
from django.conf.urls.static import static

schema_view = get_schema_view(
    openapi.Info(
        title="Blendy API",
        default_version="v1",
        description="API documentation for the Blendy project",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@blendy.local"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

schema_view.security_definitions = {
    "Bearer": {
        "type": "apiKey",
        "name": "Authorization",
        "in": "header",
        "description": "JWT Authorization header using the Bearer scheme. Example: \"Authorization: Bearer {token}\""
    },
    "X-Organization": {
        "type": "apiKey",
        "name": "X-Organization",
        "in": "header",
        "description": "Organization ID for multi-tenancy. Example: \"X-Organization: your_organization_id\""
    }
}
schema_view.security = [
    {"Bearer": []},
    {"X-Organization": []}
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("authentication.urls")),
    path("api/organization/", include("organization.urls")),
    path("api/users/", include("users.urls")),
    path("api/products/", include("products.urls")),
    path("api/authorization/", include("authorization.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/sales/", include("sales.urls")),
    path("api/pricing/", include("pricing.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path(
        "api/swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("api/redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
