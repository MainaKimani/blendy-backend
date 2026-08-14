"""Shared fixture helpers.

Pricing moved onto the pricelist, so building a sellable item now means an
organization with a default pricelist, a product, a variation, and a price entry
for that variation. These helpers keep that assembly in one place rather than
repeated across every test module.
"""

from decimal import Decimal

from organization.models import Organization
from pricing.services import create_default_pricelist, get_default_pricelist, set_price
from products.models import Product, ProductVariation


def make_organization(name="Shop", slug="shop", **kwargs):
    """An organization that can actually trade, i.e. one with a pricelist."""
    organization = Organization.objects.create(name=name, slug=slug, **kwargs)
    create_default_pricelist(organization)
    return organization


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
