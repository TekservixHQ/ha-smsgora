"""Config flow, actions, notify entity and webhook events."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.smsgora.api import SmsGoraApi, SmsGoraError, verify_signature
from custom_components.smsgora.const import (
    CONF_RECIPIENTS,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_SMS_RECEIVED,
)

API = "custom_components.smsgora.api.SmsGoraApi"


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch(f"{API}.get_account", AsyncMock(return_value={"email": "shop@example.com"})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "sgk_test_123456789", CONF_RECIPIENTS: "+1555, +1666"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SMS Gora (shop@example.com)"
    assert result["data"][CONF_RECIPIENTS] == ["+1555", "+1666"]


async def test_config_flow_invalid_key(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(f"{API}.get_account", AsyncMock(side_effect=SmsGoraError("Unauthorized", 401))):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def _setup(hass: HomeAssistant, **data) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "sgk_test", CONF_RECIPIENTS: ["+1999"], **data})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_send_sms_action(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(f"{API}.send_sms", AsyncMock(return_value={"message_ids": [1873]})) as send:
        response = await hass.services.async_call(
            DOMAIN, "send_sms", {"to": "+1555, +1666", "message": "Door opened", "sim_slot": "1"},
            blocking=True, return_response=True,
        )
    send.assert_awaited_once_with(["+1555", "+1666"], "Door opened", device_id=None, sim_slot=1)
    assert response == {"message_ids": [1873]}


async def test_notify_entity_uses_default_recipients(hass: HomeAssistant) -> None:
    await _setup(hass)
    entity_id = next(s.entity_id for s in hass.states.async_all("notify"))
    with patch(f"{API}.send_sms", AsyncMock(return_value={"message_ids": [1]})) as send:
        await hass.services.async_call(
            "notify", "send_message", {"entity_id": entity_id, "title": "Alarm", "message": "Motion"}, blocking=True
        )
    send.assert_awaited_once_with(["+1999"], "Alarm\nMotion", device_id=None)


async def test_webhook_fires_event(hass: HomeAssistant, hass_client_no_auth) -> None:
    await _setup(hass, **{CONF_WEBHOOK_ID: "abc123", CONF_WEBHOOK_SECRET: "whsec_test"})
    events = async_capture_events(hass, EVENT_SMS_RECEIVED)
    client = await hass_client_no_auth()
    raw = json.dumps({"event": "sms.received", "data": {"from": "+1555", "message": "STATUS"}}).encode()
    sig = "sha256=" + hmac.new(b"whsec_test", raw, hashlib.sha256).hexdigest()

    bad = await client.post("/api/webhook/abc123", data=raw, headers={"X-SmsGora-Signature": "sha256=bad"})
    assert bad.status == 401
    ok = await client.post("/api/webhook/abc123", data=raw, headers={"X-SmsGora-Signature": sig})
    assert ok.status == 200
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["from"] == "+1555"
    assert events[0].data["message"] == "STATUS"


async def test_api_client(hass: HomeAssistant, aioclient_mock) -> None:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.post("https://example.test/api/send-sms", json={"success": True, "data": {"message_ids": [7]}})
    aioclient_mock.get("https://example.test/api/account", status=429, json={"success": False, "message": "Too many requests"})
    api = SmsGoraApi(async_get_clientsession(hass), "sgk_test", "https://example.test/api/")
    assert await api.send_sms(["+1"], "hi") == {"message_ids": [7]}
    assert aioclient_mock.mock_calls[0][2] == {"recipients": ["+1"], "message": "hi"}
    try:
        await api.get_account()
        raise AssertionError("expected an error")
    except SmsGoraError as err:
        assert err.status == 429
        assert str(err) == "Too many requests"


def test_verify_signature() -> None:
    raw = b'{"event":"sms.received","data":{"from":"+15551234567"}}'
    sig = "sha256=e125c07dfbecb498e8979383d7b9f0815efb128755409794b486d4bbb7199583"
    assert verify_signature(raw, sig, "whsec_test")
    assert not verify_signature(raw, sig, "other")
    assert not verify_signature(raw, None, "whsec_test")
