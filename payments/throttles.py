"""Throttles for anonymous payment creation.

Guest checkout deliberately allows unauthenticated callers to create a payment,
which triggers an STK push to a phone number of their choosing. Without a limit
that is an open relay for sending M-Pesa prompts to arbitrary people, so
anonymous creates are rate limited per target phone number and per source IP.

Note: these rely on the Django cache. The default LocMemCache is per-process, so
a multi-worker deployment needs a shared backend (redis/memcached) for the
limits to actually hold.
"""

import re

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class DynamicRateThrottle(SimpleRateThrottle):
    """SimpleRateThrottle that resolves its rate at request time.

    DRF binds THROTTLE_RATES as a class attribute when the module is imported,
    so the rates are snapshotted at startup and later settings changes are
    ignored. Reading them per instance keeps the configured rate authoritative.
    """

    def get_rate(self):
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)


class STKPushPhoneThrottle(DynamicRateThrottle):
    """Limit how often an STK push can be sent to one phone number."""

    scope = "stk_push_phone"

    def get_cache_key(self, request, view):
        phone = _digits(request.data.get("phone_number", ""))
        if not phone:
            # Nothing to key on; the IP throttle still applies.
            return None
        # Key on the last 9 digits so 07…, 2547…, +2547… collapse together.
        return self.cache_format % {"scope": self.scope, "ident": phone[-9:]}


class STKPushIPThrottle(DynamicRateThrottle):
    """Limit how many STK pushes one source address can trigger."""

    scope = "stk_push_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
