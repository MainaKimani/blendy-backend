"""Shared fixture helpers.

Pricing moved onto the pricelist, so building a sellable item now means an
organization with a default pricelist, a product, a variation, and a price entry
for that variation. These helpers keep that assembly in one place rather than
repeated across every test module.
"""

from decimal import Decimal

from authorization.models import OrganizationRole, Role, UserRoleAssignment
from authorization.rbac import ORG_ADMIN, enable_default_roles
from organization.models import Organization
from pricing.services import create_default_pricelist, get_default_pricelist, set_price
from products.models import Product, ProductVariation
from users.models import CustomUser


def make_organization(name="Shop", slug="shop", **kwargs):
    """An organization shaped like one that came through onboarding.

    That means a default pricelist — without which it cannot trade — and the
    built-in roles enabled, so a user can actually be given one.
    """
    organization = Organization.objects.create(name=name, slug=slug, **kwargs)
    create_default_pricelist(organization)
    enable_default_roles()
    return organization


def grant_role(user, organization, role_name=ORG_ADMIN):
    """Give a user a seeded role inside an organization.

    Assignments run through the real Role → OrganizationRole → UserRoleAssignment
    chain rather than being faked, so a test that passes here is exercising the
    same resolution path a request does.
    """
    role = Role.objects.get(name=role_name)
    organization_role, _ = OrganizationRole.objects.get_or_create(
        organization=organization, role=role
    )
    UserRoleAssignment.objects.get_or_create(
        user=user, organization_role=organization_role
    )
    return user


def make_user(organization, email="staff@shop.test", username="staff",
              role=ORG_ADMIN, **kwargs):
    """A user who holds a role, which is what most endpoints now require."""
    user = CustomUser.objects.create_user(
        email=email, username=username, password="pw",
        organization=organization, **kwargs
    )
    if role is not None:
        grant_role(user, organization, role)
    return user


def make_priced_variation(
    organization, name, price, cost=Decimal("0.00"), **variation_kwargs
):
    """A product with one variation, priced on the organization's default list."""
    product = Product.objects.create(name=name, organization=organization)
    variation = ProductVariation.objects.create(
        product=product,
        organization=organization,
        cost_price=cost,
        **variation_kwargs,
    )
    pricelist = get_default_pricelist(organization) or create_default_pricelist(
        organization
    )
    set_price(
        organization=organization,
        pricelist=pricelist,
        product_variation=variation,
        price=Decimal(str(price)),
    )
    return variation
