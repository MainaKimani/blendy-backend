from django.utils.deprecation import MiddlewareMixin
from organization.models import Organization

class OrganizationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        organization_id = request.headers.get('X-Organization')
        if organization_id:
            try:
                organization = Organization.objects.get(id=organization_id)
                request.organization = organization
            except Organization.DoesNotExist:
                request.organization = None
        else:
            request.organization = None
