import hashlib
import hmac

from django.conf import settings


class InvalidWebhookSignature(Exception):
    pass


def verify_mpesa_signature(raw_body: bytes, provided_signature: str) -> None:
    # Expect a SHA-256 HMAC hex digest computed using the shared webhook secret.
    secret = getattr(settings, "PAYMENTS_MPESA_WEBHOOK_SECRET", "")
    if not secret:
        raise InvalidWebhookSignature("MPESA webhook secret not configured")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided_signature or ""):
        raise InvalidWebhookSignature("Invalid MPESA webhook signature")
