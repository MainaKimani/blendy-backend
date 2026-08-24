"""Resolving the platform organization.

HQ is an Organization like any other as far as the ORM is concerned, which is
what lets platform staff use the same RBAC as a shop's staff. Everywhere that
means "a customer", though, has to say so explicitly — hence `tenants()`.
"""

from .models import Organization

PLATFORM_NAME = "Blendy HQ"
PLATFORM_SLUG = "blendy-hq"


class PlatformOrganizationMissing(Exception):
    """No HQ organization exists. Run `manage.py bootstrap_hq`."""


def get_platform_organization():
    """Blendy's own HQ, or None if it has not been created yet."""
    return Organization.objects.filter(is_platform=True).first()


def require_platform_organization():
    organization = get_platform_organization()
    if organization is None:
        raise PlatformOrganizationMissing(
            "No platform organization exists. Run `manage.py bootstrap_hq`."
        )
    return organization


def tenants():
    """Customer organizations — every organization except HQ.

    Use this anywhere the answer means "a shop": listings, counts, billing, and
    the M-Pesa shortcode fallback. `Organization.objects.all()` now includes
    ourselves, and treating HQ as a customer is how a shop's money gets
    attributed to the wrong place.
    """
    return Organization.objects.filter(is_platform=False)


def create_platform_organization(name=PLATFORM_NAME, slug=PLATFORM_SLUG):
    """Create HQ, or return the existing one.

    Deliberately does not go through onboarding: HQ needs no pricelist and no
    shop roles, because it never sells anything.
    """
    existing = get_platform_organization()
    if existing is not None:
        return existing, False

    organization = Organization.objects.create(
        name=name, slug=slug, is_platform=True
    )
    return organization, True
