from .base import BasePaymentProvider, ProviderChargeResult


class MpesaPaymentProvider(BasePaymentProvider):
    """MPESA adapter.

    `create_charge` is intentionally a stub for now so Phase 2 can ship webhook
    provider boundaries before the live API client is introduced.
    """

    provider_name = "MPESA"

    def create_charge(self, *, amount, currency: str, phone_number: str, idempotency_key: str) -> ProviderChargeResult:
        # Placeholder stub until full gateway credentials + API integration are added.
        return ProviderChargeResult(
            reference=f"mpesa_stub_{idempotency_key}",
            status="PENDING",
            raw_response={
                "message": "MPESA integration stub accepted request",
                "amount": str(amount),
                "currency": currency,
                "phone_number": phone_number,
            },
        )

    def parse_webhook_payload(self, payload: dict):
        # Normalize multiple possible MPESA callback payload field names.
        return {
            "provider_reference": payload.get("provider_reference") or payload.get("CheckoutRequestID", ""),
            "status": payload.get("status") or payload.get("ResultCode"),
            "failure_reason": payload.get("failure_reason") or payload.get("ResultDesc", ""),
        }
