import base64
import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from decouple import config

from .base import BasePaymentProvider, ProviderChargeResult


class MpesaPaymentProvider(BasePaymentProvider):
    """MPESA adapter.

    `create_charge` is intentionally a stub for now so Phase 2 can ship webhook
    provider boundaries before the live API client is introduced.
    """

    provider_name = "MPESA"

    def _get_setting(self, key: str, default: str = "") -> str:
        return config(key, default=default)

    def _get_access_token(self) -> str:
        consumer_key = self._get_setting("MPESA_CONSUMER_KEY")
        consumer_secret = self._get_setting("MPESA_CONSUMER_SECRET")
        base_url = self._get_setting("MPESA_BASE_URL", "https://sandbox.safaricom.co.ke")

        if not consumer_key or not consumer_secret:
            raise ValueError("Missing MPESA consumer credentials")

        auth_string = f"{consumer_key}:{consumer_secret}".encode("utf-8")
        auth_header = base64.b64encode(auth_string).decode("utf-8")
        url = f"{base_url}/oauth/v1/generate?{urlencode({'grant_type': 'client_credentials'})}"
        request = Request(url, headers={"Authorization": f"Basic {auth_header}"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        token = payload.get("access_token")
        if not token:
            raise ValueError("Failed to obtain MPESA access token")
        return token

    def _build_password(self, timestamp: str) -> str:
        shortcode = self._get_setting("MPESA_SHORTCODE")
        passkey = self._get_setting("MPESA_PASSKEY")
        if not shortcode or not passkey:
            raise ValueError("Missing MPESA shortcode/passkey")
        raw = f"{shortcode}{passkey}{timestamp}".encode("utf-8")
        return base64.b64encode(raw).decode("utf-8")

    def create_charge(self, *, amount, currency: str, phone_number: str, idempotency_key: str) -> ProviderChargeResult:
        base_url = self._get_setting("MPESA_BASE_URL", "https://sandbox.safaricom.co.ke")
        callback_url = self._get_setting("MPESA_CALLBACK_URL")
        if not callback_url:
            raise ValueError("MPESA_CALLBACK_URL is required for STK Push")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        token = self._get_access_token()
        shortcode = self._get_setting("MPESA_SHORTCODE")
        account_reference = self._get_setting("MPESA_ACCOUNT_REFERENCE", "Mitchy Fits")
        transaction_desc = self._get_setting("MPESA_TRANSACTION_DESC", "Payment")

        payload = {
            "BusinessShortCode": shortcode,
            "Password": self._build_password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number.replace("+", ""),
            "PartyB": shortcode,
            "PhoneNumber": phone_number.replace("+", ""),
            "CallBackURL": callback_url,
            "AccountReference": account_reference,
            "TransactionDesc": transaction_desc,
        }

        request = Request(
            f"{base_url}/mpesa/stkpush/v1/processrequest",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            raise ValueError(f"MPESA STK request failed: {detail}") from exc
        except URLError as exc:
            raise ValueError(f"MPESA STK request error: {exc.reason}") from exc

        provider_reference = response_payload.get("CheckoutRequestID") or ""
        if not provider_reference:
            raise ValueError("MPESA did not return a checkout request ID")
        merchant_reference = response_payload.get("MerchantRequestID") or ""
        if not merchant_reference:
            raise ValueError("MPESA did not return a merchant request ID")

        return ProviderChargeResult(
            provider_reference=provider_reference,
            merchant_reference=merchant_reference,
            status="PENDING",
            raw_response=response_payload,
        )

    def parse_webhook_payload(self, payload: dict):
        response_data = payload.get("Body", {}).get("stkCallback", {})
        if not response_data:
            raise ValueError("Invalid MPESA webhook payload: missing Body.stkCallback")
        metadata = response_data.get("CallbackMetadata")
        if metadata and "Item" in metadata:
            items = metadata["Item"]
            # Use a dictionary comprehension to flatten the 'Item' list into a single dictionary
            parsed_data = {item["Name"]: item.get("Value") for item in items}

        payload = {
            "checkout_request_id": response_data.get("CheckoutRequestID"),
            "merchant_request_id": response_data.get("MerchantRequestID"),
            "phone_number:": parsed_data.get("PhoneNumber") if metadata else None,
            "amount": parsed_data.get("Amount") if metadata else None,
            "transaction_date": parsed_data.get("TransactionDate") if metadata else None,
            "mpesa_receipt_number": parsed_data.get("MpesaReceiptNumber") if metadata else None,
            "amount": parsed_data.get("Amount") if metadata else None,
            "ResultCode": response_data.get("ResultCode"),
            "ResultDesc": response_data.get("ResultDesc"),
        }
        return payload
