"""Stock movement services.

Every stock change goes through `record_movement`. It appends to the
StockMovement ledger (the source of truth) and updates the cached balance on
InventoryItem inside the same transaction, taking a row lock so concurrent
sales cannot oversell.
"""

from django.db import transaction
from django.db.models import Sum

from .models import InventoryItem, Location, StockMovement


class InsufficientStock(Exception):
    """Raised when a movement would drive a variation's stock below zero."""

    def __init__(self, product_variation, requested, available):
        self.product_variation = product_variation
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for {product_variation.name}: "
            f"requested {requested}, available {available}."
        )


def get_default_location(organization):
    """Return the organization's default stock location, creating it if absent.

    Multi-branch is out of MVP scope, so each organization has exactly one
    location that stock moves through. `code` is globally unique, hence the
    slug suffix.
    """
    location = Location.objects.filter(
        organization=organization, is_default=True
    ).first()
    if location is not None:
        return location

    location, _ = Location.objects.get_or_create(
        organization=organization,
        code=f"MAIN-{organization.slug}",
        defaults={"name": "Main Store", "is_default": True},
    )
    if not location.is_default:
        location.is_default = True
        location.save(update_fields=["is_default"])
    return location


@transaction.atomic
def record_movement(
    *,
    organization,
    product_variation,
    movement_type,
    quantity,
    location=None,
    user=None,
    reference_number="",
    notes="",
    unit_cost=None,
    allow_negative=False,
):
    """Append a ledger entry and update the cached balance atomically.

    `quantity` is signed: negative removes stock, positive adds it. Returns the
    created StockMovement. Raises InsufficientStock when an outflow would take
    the balance below zero, unless `allow_negative` is set (used by corrections
    that must be recorded even when they produce a negative balance).
    """
    if quantity == 0:
        raise ValueError("Stock movement quantity cannot be zero.")

    if location is None:
        location = get_default_location(organization)

    # Lock the balance row for the duration of the transaction so two concurrent
    # sales of the last unit cannot both pass the availability check.
    item = (
        InventoryItem.objects.select_for_update()
        .filter(
            organization=organization,
            product_variation=product_variation,
            location=location,
        )
        .first()
    )
    if item is None:
        item = InventoryItem.objects.create(
            organization=organization,
            product_variation=product_variation,
            location=location,
            available_quantity=0,
        )
        item = (
            InventoryItem.objects.select_for_update()
            .filter(pk=item.pk)
            .first()
        )

    new_quantity = item.available_quantity + quantity
    if new_quantity < 0 and not allow_negative:
        raise InsufficientStock(
            product_variation=product_variation,
            requested=abs(quantity),
            available=item.available_quantity,
        )

    movement = StockMovement.objects.create(
        organization=organization,
        product_variation=product_variation,
        location=location,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=unit_cost,
        reference_number=reference_number,
        notes=notes,
        created_by=user,
    )

    item.available_quantity = new_quantity
    item.updated_by = user
    item.save(update_fields=["available_quantity", "updated_by", "last_updated"])

    return movement


@transaction.atomic
def set_stock_level(
    *,
    organization,
    product_variation,
    counted_quantity,
    location=None,
    user=None,
    notes="",
    reference_number="",
):
    """Correct stock to a physically counted figure (US-19).

    The difference is computed under the same row lock that writes it, so a sale
    landing between the count being read and applied cannot be silently undone.
    Returns the ledger entry, or None when the count already matched.
    """
    if location is None:
        location = get_default_location(organization)

    item = (
        InventoryItem.objects.select_for_update()
        .filter(
            organization=organization,
            product_variation=product_variation,
            location=location,
        )
        .first()
    )
    current = item.available_quantity if item is not None else 0
    delta = counted_quantity - current
    if delta == 0:
        return None

    return record_movement(
        organization=organization,
        product_variation=product_variation,
        movement_type="ADJUSTMENT",
        quantity=delta,
        location=location,
        user=user,
        reference_number=reference_number,
        notes=notes,
        # A count is authoritative about what is physically on the shelf.
        allow_negative=True,
    )


def ledger_balance(organization, product_variation, location=None):
    """Current stock derived from the ledger itself, ignoring the cache.

    Use this to audit or rebuild InventoryItem.available_quantity.
    """
    movements = StockMovement.objects.filter(
        organization=organization, product_variation=product_variation
    )
    if location is not None:
        movements = movements.filter(location=location)
    return movements.aggregate(balance=Sum("quantity"))["balance"] or 0
