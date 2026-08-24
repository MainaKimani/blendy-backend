"""Recording cross-tenant access.

Placed in middleware rather than in the permission class on purpose. A view that
forgets to apply IsOrganizationUser would slip past a permission-class hook
unlogged, and a denial never reaches the permission class's success path at all.
Deciding here, from the request and its response, catches both.
"""

from django.utils.deprecation import MiddlewareMixin


class PlatformAccessLogMiddleware(MiddlewareMixin):
    """Log every request that reaches an organization the caller is not in.

    Runs on the way *out*, because DRF authenticates inside the view: on the way
    in, request.user is still anonymous for a JWT-authenticated call.
    """

    # No tenant is named on these, so there is no cross-tenant access to record.
    EXEMPT_PREFIXES = ("/api/swagger", "/api/redoc", "/admin", "/static", "/media")

    def process_response(self, request, response):
        try:
            self._record(request, response)
        except Exception:
            # Never fail a request because its audit row could not be written.
            # The alternative — a 500 on the logging path — would make the
            # safest thing to do about auditing be to remove it.
            pass
        return response

    def _record(self, request, response):
        path = request.path
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return

        organization = getattr(request, "organization", None)
        if organization is None:
            # No tenant named, so nothing was crossed into.
            return

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return

        if user.organization_id == organization.id:
            # An ordinary member of this organization. Logging every such
            # request would bury the ones that matter.
            return

        from .models import PlatformAccessLog

        PlatformAccessLog.objects.create(
            actor=user,
            actor_email=user.email,
            actor_is_platform=bool(
                getattr(user.organization, "is_platform", False)
                or user.is_superuser_admin
            ),
            organization=organization,
            organization_slug=organization.slug,
            method=request.method,
            path=path[:500],
            status_code=response.status_code,
            granted=response.status_code < 400,
        )
