"""Kenyan phone number normalisation.

Extracted from PaymentSerializer so the direct-payment matcher can compare an
inbound MSISDN against a sale's stored customer phone using identical rules.
Raises ValueError; API layers translate that into a validation error.
"""

import re

SAFARICOM_PREFIXES = {
    "25470",
    "25471",
    "25472",
    "25474",
    "25475",
    "25476",
    "25477",
    "25479",
    "25410",
    "25411",
}

INVALID_NUMBER_MESSAGE = (
    "Enter a valid Kenyan phone number (e.g. +2547XXXXXXXX or 07XXXXXXXX)."
)
NON_SAFARICOM_MESSAGE = "M-Pesa payments require a Safaricom phone number."


def normalize_kenyan_phone(phone_number):
    """Return the number in canonical +2547XXXXXXXX form."""
    if not phone_number:
        raise ValueError("Phone number is required for payments.")

    # Remove spaces, dashes and parentheses while preserving the leading +.
    cleaned = re.sub(r"[^\d+]", "", str(phone_number).strip())
    digits_only = cleaned.replace("+", "")

    if digits_only.startswith("0") and len(digits_only) == 10:
        digits_only = f"254{digits_only[1:]}"
    elif digits_only.startswith("254") and len(digits_only) == 12:
        pass
    elif digits_only.startswith("7") and len(digits_only) == 9:
        digits_only = f"254{digits_only}"
    elif digits_only.startswith("1") and len(digits_only) == 9:
        digits_only = f"254{digits_only}"
    else:
        raise ValueError(INVALID_NUMBER_MESSAGE)

    return f"+{digits_only}"


def validate_safaricom_phone(normalized_phone):
    digits = normalized_phone.replace("+", "")
    if digits[:5] not in SAFARICOM_PREFIXES:
        raise ValueError(NON_SAFARICOM_MESSAGE)


def normalize_for_matching(phone_number):
    """Best-effort normalisation for comparison; returns None if unparseable.

    Sale.customer_phone is free text captured at checkout, so a stored value may
    not be a valid number at all. Matching must skip those rather than blow up.
    """
    try:
        return normalize_kenyan_phone(phone_number)
    except ValueError:
        return None
