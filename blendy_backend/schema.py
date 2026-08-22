"""Schema generation for the published API documentation.

Two things drf-yasg cannot work out on its own:

1. **Authentication.** The project authenticates with JWT bearer tokens, but
   drf-yasg defaults to declaring HTTP Basic. `SWAGGER_SETTINGS` in settings.py
   corrects that.

2. **Tenancy.** Almost every endpoint is scoped by an `X-Organization` header
   read by OrganizationMiddleware, not by any serializer or view attribute, so
   nothing in the code tells the schema generator it exists. Without it the
   documentation omits the one header a client cannot work without — and a
   caller who omits it gets an empty list rather than an error, because the
   viewsets fail closed. It is added here for every operation except the handful
   that are genuinely tenant-free.
"""

from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator

# Defined here rather than inline in urls.py so both the live Swagger UI and the
# `generate_swagger` management command describe the API identically.
API_INFO = openapi.Info(
    title="Blendy API",
    default_version="v1",
    description=(
        "Backend for Blendy, a point-of-sale and inventory system for Kenyan "
        "retail SMEs.\n\n"
        "**Tenancy.** Every tenant-scoped endpoint reads the organization from "
        "an `X-Organization` header. Requests without it resolve to no tenant, "
        "and the viewsets fail closed — reads return an empty result set and "
        "writes are refused.\n\n"
        "**Authentication.** JWT bearer tokens from `/api/auth/login/`. Two "
        "paths stay open to anonymous callers so guest checkout works: creating "
        "a sale and creating a payment against it.\n\n"
        "**Pricing.** Prices live on a pricelist, not on the product. Each "
        "organization gets a `Default Pricelist` at onboarding, and a sale is "
        "priced from it — an organization without one cannot transact."
    ),
    terms_of_service="https://www.google.com/policies/terms/",
    contact=openapi.Contact(email="contact@blendy.local"),
    license=openapi.License(name="BSD License"),
)

ORGANIZATION_HEADER = openapi.Parameter(
    name="X-Organization",
    in_=openapi.IN_HEADER,
    description=(
        "The organization (tenant) the request applies to. Required for every "
        "tenant-scoped endpoint: without it the request resolves to no tenant "
        "and reads return an empty result set rather than an error."
    ),
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
    required=True,
)

# Paths that are deliberately tenant-free.
#   /auth/, /token/      — you cannot know your organization before signing in
#   /organization/       — creating and onboarding organizations
#   /authorization/permissions/, /authorization/roles/ — global catalogues,
#                          superadmin only
#   /payments/webhooks/  — called by Safaricom, authenticated by URL token + IP
TENANT_FREE_PREFIXES = (
    "/auth/",
    "/token/",
    "/organization/",
    "/authorization/permissions/",
    "/authorization/roles/",
    "/payments/webhooks/",
    "/users/register/",
)


def is_tenant_scoped(path):
    return not any(path.startswith(prefix) for prefix in TENANT_FREE_PREFIXES)


class BlendySchemaGenerator(OpenAPISchemaGenerator):
    """Adds the tenancy header to every operation that needs one."""

    def get_operation(self, view, path, prefix, method, components, request):
        operation = super().get_operation(
            view, path, prefix, method, components, request
        )
        if operation is None:
            return None

        # `path` here still carries the basePath prefix, so compare on the
        # portion after it.
        relative = path[len("/api") :] if path.startswith("/api") else path
        if is_tenant_scoped(relative):
            operation.parameters = list(operation.parameters) + [ORGANIZATION_HEADER]

        return operation
