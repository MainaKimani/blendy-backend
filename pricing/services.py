"""Pricelist resolution.

The pricelist is authoritative for selling prices: a product carries no price of
its own, and a sale is priced from the organization's default pricelist. An
organization without one cannot transact, and a variation with no entry on the
list cannot be sold — both are refused rather than guessed at.

Cost is deliberately not held here. It belongs to the item, not to a price list:
`ProductVariation.cost_price` is the standing cost and `StockMovement.unit_cost`
records what each receipt actually cost. Both are snapshotted onto the sale line
so history survives later price changes.
"""

from .models import Pricelist, PricelistItem

DEFAULT_PRICELIST_NAME = "Default Pricelist"


class PricelistUnavailable(Exception):
    """The organization has no default pricelist, so it cannot sell anything."""


class VariationNotPriced(Exception):
    """The variation has no entry on the pricelist being sold from."""

    def __init__(self, product_variation, pricelist):
        self.product_variation = product_variation
        self.pricelist = pricelist
        super().__init__(
            f"{product_variation.name} has no price on '{pricelist.name}'. "
            "Add it to the pricelist before selling it."
        )


def create_default_pricelist(organization):
    """Give an organization the pricelist it needs in order to trade."""
    pricelist, _ = Pricelist.objects.get_or_create(
        organization=organization,
        is_default=True,
        defaults={
            "name": DEFAULT_PRICELIST_NAME,
            "description": "Prices used for sales unless another list applies.",
        },
    )
    return pricelist


def get_default_pricelist(organization):
    """Return the organization's default pricelist, or None if it has none.

    `organization` may be an Organization or just its id. Passing the id is
    preferred when serializing, since it avoids a foreign-key fetch per row.

    Deliberately does not create one on demand: a missing pricelist should stop
    a sale and be fixed by an owner, not be papered over mid-transaction.
    """
    return Pricelist.objects.filter(
        organization=organization, is_default=True, is_active=True
    ).first()


def require_default_pricelist(organization):
    pricelist = get_default_pricelist(organization)
    if pricelist is None:
        raise PricelistUnavailable(
            "This organization has no active default pricelist, so nothing can "
            "be sold. Create one before recording sales."
        )
    return pricelist


def get_price(pricelist, product_variation):
    """The selling price for a variation on a given list, or None."""
    item = PricelistItem.objects.filter(
        pricelist=pricelist, product_variation=product_variation
    ).first()
    return item.price if item is not None else None


def require_price(pricelist, product_variation):
    price = get_price(pricelist, product_variation)
    if price is None:
        raise VariationNotPriced(product_variation, pricelist)
    return price


def get_prices(pricelist, product_variations):
    """Prices for several variations on one list, keyed by variation id.

    One query for the whole basket. Resolving a sale line at a time cost a query
    per line, which is the same lookup repeated against the same list.
    """
    return dict(
        PricelistItem.objects.filter(
            pricelist=pricelist, product_variation__in=product_variations
        ).values_list("product_variation_id", "price")
    )


def set_price(*, organization, pricelist, product_variation, price):
    """Record or update a variation's price on a list."""
    item, _ = PricelistItem.objects.update_or_create(
        pricelist=pricelist,
        product_variation=product_variation,
        defaults={"price": price, "organization": organization},
    )
    return item
