"""SMS Gora for Home Assistant: send SMS through your own Android phones and react to incoming SMS."""

from __future__ import annotations

import json
import logging
import secrets

import voluptuous as vol
from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.helpers.typing import ConfigType

from .api import SmsGoraApi, SmsGoraError, split_numbers, verify_signature
from .const import (
    CONF_DEVICE_ID,
    CONF_REMOTE_WEBHOOK_ID,
    CONF_WEBHOOK_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_SMS_RECEIVED,
    EVENT_SMS_STATUS,
    SERVICE_SEND_SMS,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.NOTIFY]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SEND_SMS_SCHEMA = vol.Schema(
    {
        vol.Required("to"): vol.Any(cv.string, [cv.string]),
        vol.Required("message"): cv.string,
        vol.Optional("device_id"): cv.string,
        vol.Optional("sim_slot"): vol.All(vol.Coerce(int), vol.In([0, 1])),
    }
)

type SmsGoraConfigEntry = ConfigEntry[SmsGoraApi]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the smsgora.send_sms action."""

    async def send_sms(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("SMS Gora is not set up")
        entry = entries[0]
        to = split_numbers(call.data["to"])
        try:
            result = await entry.runtime_data.send_sms(
                to,
                call.data["message"],
                device_id=call.data.get("device_id") or entry.data.get(CONF_DEVICE_ID),
                sim_slot=call.data.get("sim_slot"),
            )
        except (SmsGoraError, ValueError) as err:
            raise HomeAssistantError(f"SMS Gora: {err}") from err
        return result if isinstance(result, dict) else {"result": result}

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_SMS, send_sms, schema=SEND_SMS_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmsGoraConfigEntry) -> bool:
    """Set up SMS Gora from a config entry."""
    api = SmsGoraApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    entry.runtime_data = api

    # Incoming SMS and delivery reports: a Home Assistant webhook, registered in SMS Gora
    # automatically when Home Assistant has an external URL (e.g. Nabu Casa or your domain).
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = secrets.token_hex(16)
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_WEBHOOK_ID: webhook_id})
    webhook.async_register(hass, DOMAIN, "SMS Gora", webhook_id, _handle_webhook, allowed_methods=["POST"])

    if not entry.data.get(CONF_REMOTE_WEBHOOK_ID):
        try:
            url = webhook.async_generate_url(hass, webhook_id, allow_internal=False)
        except NoURLAvailableError:
            _LOGGER.info("SMS Gora: no external URL, so incoming SMS events are off (sending still works)")
        else:
            try:
                created = await api.create_webhook(url, ["sms.received", "sms.delivered", "sms.failed"])
            except SmsGoraError as err:
                _LOGGER.warning("SMS Gora: could not register the webhook: %s", err)
            else:
                if isinstance(created, dict) and created.get("id") is not None:
                    hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_REMOTE_WEBHOOK_ID: created["id"],
                            CONF_WEBHOOK_SECRET: created.get("secret", ""),
                        },
                    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmsGoraConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.data.get(CONF_WEBHOOK_ID):
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: SmsGoraConfigEntry) -> None:
    """Remove the webhook from SMS Gora when the integration is deleted."""
    remote = entry.data.get(CONF_REMOTE_WEBHOOK_ID)
    if remote is None:
        return
    api = SmsGoraApi(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    try:
        await api.delete_webhook(remote)
    except SmsGoraError as err:
        _LOGGER.warning("SMS Gora: could not delete webhook %s: %s", remote, err)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
    """Check the signature and fire smsgora_sms_received / smsgora_sms_status events."""
    entry = next(
        (e for e in hass.config_entries.async_entries(DOMAIN) if e.data.get(CONF_WEBHOOK_ID) == webhook_id), None
    )
    if entry is None:
        return web.Response(status=404)
    raw = await request.read()
    secret = entry.data.get(CONF_WEBHOOK_SECRET)
    if not secret or not verify_signature(raw, request.headers.get("X-SmsGora-Signature"), secret):
        return web.Response(status=401, text="bad signature")
    try:
        event = json.loads(raw)
    except ValueError:
        return web.Response(status=400)
    name = event.get("event", "")
    data = event.get("data") or {}
    if name == "sms.received":
        hass.bus.async_fire(EVENT_SMS_RECEIVED, {"from": data.get("from"), "message": data.get("message"), **data})
    else:
        hass.bus.async_fire(EVENT_SMS_STATUS, {"event": name, **data})
    return web.Response(text="ok")
