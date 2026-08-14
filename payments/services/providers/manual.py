import uuid

from .base import BasePaymentProvider, ProviderChargeResult


class ManualPaymentProvider(BasePaymentProvider):
    """Internal provider used for controlled/manual testing scenarios."""

    provider_name = "MANUAL"

    def create_charge(self, *, amount, currency: str, phone_number: str, idempotency_key: str) -> ProviderChargeResult:
        return ProviderChargeResult(
            provider_reference=f"manual_{uuid.uuid4().hex}",
            merchant_reference=f"manual_merchant_{uuid.uuid4().hex}",
            status="PENDING",
            raw_response={"simulated": True, "idempotency_key": idempotency_key},
        )

    def parse_webhook_payload(self, payload: dict):
        return payload
