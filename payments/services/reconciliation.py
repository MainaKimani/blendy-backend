"""Direct (non-STK) M-Pesa payment reconciliation.

Implements the fallback path in MVP §8 / US-9b / US-9c: when an STK push fails,
the sale stays open in AWAITING_DIRECT_PAYMENT and the customer pays the Till
directly. The resulting C2B confirmation carries no sale reference — only a
phone number, an amount and a shortcode — so the sale has to be found by
matching those.

Matching is deliberately conservative: it reconciles only when exactly one open
sale matches on tenant, phone, amount and recency. Zero or several candidates
leave the payment unmatched and queryable, never guessed at.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from organization.models import Organization
from sales.models import Sale

from ..models import MpesaTransaction, Payment
from .phone import normalize_for_matching


class TenantNotResolved(Exception):
    """The inbound confirmation could not be attributed to an organization."""


@dataclass
class MatchResult:
    sale: "Sale | None"
    candidates: list
    note: str

    @property
    def matched(self):
        return self.sale is not None


def _match_window():
    hours = getattr(settings, "MPESA_DIRECT_MATCH_WINDOW_HOURS", 24)
    return timedelta(hours=hours)


def _amount_tolerance():
    return Decimal(str(getattr(settings, "MPESA_DIRECT_MATCH_TOLERANCE", "0.00")))


def parse_mpesa_timestamp(value):
    """Parse M-Pesa's YYYYMMDDHHMMSS timestamp into an aware datetime.

    M-Pesa reports in East Africa Time; the project stores UTC, so the naive
    value is localised before conversion. Returns None if unparseable.
    """
    if value in (None, ""):
        return None
    try:
        naive = datetime.strptime(str(value).strip(), "%Y%m%d%H%M%S")
    except (ValueError, TypeError):
        return None
    return naive.replace(tzinfo=ZoneInfo("Africa/Nairobi"))


def to_decimal(value):
    """Coerce an M-Pesa amount to Decimal, or None when it is unusable."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def resolve_organization(shortcode):
    """Find the tenant that owns an inbound confirmation.

    Prefers an explicit per-tenant shortcode. While a deployment still runs the
    single shared shortcode from settings, fall back to the only organization
    present so existing single-tenant setups keep working.
    """
    shortcode = str(shortcode or "").strip()

    if shortcode:
        organization = Organization.objects.filter(
            mpesa_shortcode=shortcode
        ).first()
        if organization is not None:
            return organization

    configured = str(getattr(settings, "MPESA_SHORTCODE", "") or "").strip()
    if shortcode and configured and shortcode == configured:
        organizations = list(Organization.objects.all()[:2])
        if len(organizations) == 1:
            return organizations[0]

    raise TenantNotResolved(
        f"No organization is registered for M-Pesa shortcode {shortcode!r}."
    )


def find_matching_sale(organization, phone_number, amount, now=None):
    """Find the single open sale an inbound direct payment belongs to."""
    now = now or timezone.now()

    normalized = normalize_for_matching(phone_number)
    if normalized is None:
        return MatchResult(None, [], f"Unparseable payer phone number {phone_number!r}.")

    amount = to_decimal(amount)
    if amount is None:
        return MatchResult(None, [], "Inbound payment had no usable amount.")

    open_sales = Sale.objects.filter(
        organization=organization,
        payment_status__in=Sale.OPEN_FOR_DIRECT_PAYMENT,
        created_at__gte=now - _match_window(),
    ).prefetch_related("items")

    tolerance = _amount_tolerance()
    candidates = [
        sale
        for sale in open_sales
        if normalize_for_matching(sale.customer_phone) == normalized
        and abs(sale.total_amount - amount) <= tolerance
    ]

    if not candidates:
        return MatchResult(
            None,
            [],
            f"No open sale within the match window for {normalized} at {amount}.",
        )

    if len(candidates) > 1:
        # Never guess which sale the money belongs to.
        ids = ", ".join(str(sale.id) for sale in candidates)
        return MatchResult(
            None,
            candidates,
            f"Ambiguous: {len(candidates)} open sales match {normalized} at "
            f"{amount} ({ids}). Needs manual matching.",
        )

    return MatchResult(candidates[0], candidates, "")


@transaction.atomic
def reconcile_direct_payment(
    *,
    organization,
    phone_number,
    amount,
    provider_reference,
    transaction_date=None,
    raw_description="",
):
    """Record an inbound direct payment and reconcile it if it matches a sale.

    Returns the created MpesaTransaction. When a single open sale matches, a
    SUCCEEDED Payment is attached and the sale is marked PAID; otherwise the
    transaction is stored unmatched with a note explaining why, so it stays
    visible in the pending queue.
    """
    existing = MpesaTransaction.objects.filter(
        organization=organization, mpesa_receipt_number=provider_reference
    ).first()
    if existing is not None:
        # M-Pesa retries confirmations; never double-credit a sale.
        return existing

    amount_value = to_decimal(amount)
    result = find_matching_sale(organization, phone_number, amount)

    payment = None
    if result.matched:
        payment = Payment.objects.create(
            organization=organization,
            sale=result.sale,
            provider=Payment.ProviderChoices.MPESA,
            status=Payment.StatusChoices.SUCCEEDED,
            amount=amount_value,
            phone_number=normalize_for_matching(phone_number),
            provider_reference=provider_reference,
            reconciliation_status=Payment.ReconciliationStatus.MATCHED,
            reconciled_at=timezone.now(),
            paid_at=transaction_date or timezone.now(),
        )
        result.sale.payment_status = "PAID"
        result.sale.save(update_fields=["payment_status"])

    return MpesaTransaction.objects.create(
        organization=organization,
        merchant_request_id="",
        checkout_request_id="",
        phone_number=phone_number,
        amount=amount_value,
        result_code="0",
        description=raw_description,
        mpesa_receipt_number=provider_reference,
        transaction_date=transaction_date,
        payment=payment,
        reconciliation_note=result.note,
    )
