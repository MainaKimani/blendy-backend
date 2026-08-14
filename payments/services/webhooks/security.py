"""Authentication for inbound M-Pesa callbacks.

Safaricom does not sign STK callbacks, so there is no shared-secret HMAC to
verify on the real integration. Instead the callback is authenticated by two
independent factors:

1. An unguessable token embedded in the callback URL path, which only Safaricom
   knows because it is what was registered with Daraja.
2. The source IP, checked against Safaricom's published egress ranges.

The HMAC path in `signature.py` is retained for the MANUAL provider, which is
driven by our own test harness and can sign its requests.
"""

import hmac

from django.conf import settings


class WebhookAuthenticationFailed(Exception):
    pass


def _client_ip(request) -> str:
    if getattr(settings, "MPESA_WEBHOOK_TRUST_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # Left-most entry is the original client when the proxy appends.
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def verify_callback_token(provided_token: str) -> None:
    expected = getattr(settings, "MPESA_WEBHOOK_TOKEN", "")
    if not expected:
        # Fail closed: an unconfigured token must not mean "accept anything".
        raise WebhookAuthenticationFailed("MPESA webhook token is not configured")
    if not hmac.compare_digest(expected, provided_token or ""):
        raise WebhookAuthenticationFailed("Invalid MPESA webhook token")


def verify_callback_source_ip(request) -> None:
    if not getattr(settings, "MPESA_WEBHOOK_ENFORCE_IP", True):
        return

    allowlist = getattr(settings, "MPESA_WEBHOOK_IP_ALLOWLIST", [])
    if not allowlist:
        return

    if _client_ip(request) not in allowlist:
        raise WebhookAuthenticationFailed("Callback source IP is not allowlisted")


def authenticate_mpesa_callback(request, provided_token: str) -> None:
    """Raise WebhookAuthenticationFailed unless the callback is trustworthy."""
    verify_callback_token(provided_token)
    verify_callback_source_ip(request)
