from payments.models import Payment

from .manual import ManualPaymentProvider
from .mpesa import MpesaPaymentProvider


def get_provider(provider_name: str):
    # Centralized provider resolution keeps gateway-specific imports out of views.
    if provider_name == Payment.ProviderChoices.MANUAL:
        return ManualPaymentProvider()
    if provider_name == Payment.ProviderChoices.MPESA:
        return MpesaPaymentProvider()
    raise ValueError(f"Unsupported payment provider: {provider_name}")
