from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderChargeResult:
    """Standard response shape returned by provider adapters."""

    reference: str
    status: str
    raw_response: dict[str, Any]


class BasePaymentProvider:
    """Contract implemented by all payment provider adapters."""

    provider_name: str

    def create_charge(self, *, amount, currency: str, phone_number: str, idempotency_key: str) -> ProviderChargeResult:
        raise NotImplementedError

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
