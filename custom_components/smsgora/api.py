"""Small async client for the SMS Gora API (no Home Assistant imports, so it can be tested alone)."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL


class SmsGoraError(Exception):
    """The API answered with an error (status 0 when it was not reached)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class SmsGoraApi:
    """Calls the SMS Gora API with the customer's own API key."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        if not api_key:
            raise ValueError("SMS Gora: an API key is required (SMS Gora -> API keys)")
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call any documented endpoint and return its `data`."""
        headers = {"x-api-key": self._api_key, "Accept": "application/json", "User-Agent": "smsgora-homeassistant/1.0.0"}
        try:
            async with self._session.request(
                method, self._base_url + path, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SmsGoraError(f"request failed ({err})") from err
        try:
            data = await _json(text)
        except ValueError:
            data = None
        if status >= 400 or (isinstance(data, dict) and data.get("success") is False):
            message = data.get("message") if isinstance(data, dict) and isinstance(data.get("message"), str) else f"HTTP {status}"
            raise SmsGoraError(message, status)
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    async def send_sms(
        self, recipients: list[str], message: str, device_id: str | None = None, sim_slot: int | None = None
    ) -> Any:
        """Send an SMS to up to 1,000 numbers."""
        if not recipients:
            raise ValueError("send_sms: at least one recipient is required")
        body: dict[str, Any] = {"recipients": recipients, "message": message}
        if sim_slot is not None:
            body["sim_slot"] = sim_slot
        path = f"/devices/{device_id}/send-sms" if device_id else "/send-sms"
        return await self.request("POST", path, body)

    async def get_account(self) -> Any:
        """Account, plan and usage (also used to check the key)."""
        return await self.request("GET", "/account")

    async def create_webhook(self, url: str, events: list[str]) -> Any:
        """Register a webhook; the answer holds its id and secret."""
        return await self.request("POST", "/webhooks", {"url": url, "events": events, "device_id": None})

    async def delete_webhook(self, webhook_id: str | int) -> Any:
        return await self.request("DELETE", f"/webhooks/{webhook_id}")


async def _json(text: str) -> Any:
    import json

    return json.loads(text) if text else None


def split_numbers(value: str | list[str] | None) -> list[str]:
    """Accept '+1555, +1666' or a list."""
    if value is None:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [str(i).strip() for i in items if str(i).strip()]


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """Check X-SmsGora-Signature (sha256=<hex HMAC-SHA256 of the raw body>) in constant time."""
    if not raw_body or not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
