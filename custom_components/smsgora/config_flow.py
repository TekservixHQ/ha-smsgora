"""Config flow for SMS Gora: asks for the API key and default recipients."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmsGoraApi, SmsGoraError, split_numbers
from .const import CONF_DEVICE_ID, CONF_RECIPIENTS, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_RECIPIENTS, default=""): str,
        vol.Optional(CONF_DEVICE_ID, default=""): str,
    }
)


class SmsGoraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up SMS Gora from the UI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = SmsGoraApi(async_get_clientsession(self.hass), user_input[CONF_API_KEY])
            try:
                account = await api.get_account()
            except SmsGoraError as err:
                errors["base"] = "invalid_auth" if err.status in (401, 403) else "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_API_KEY][-12:])
                self._abort_if_unique_id_configured()
                title = "SMS Gora"
                if isinstance(account, dict) and account.get("email"):
                    title = f"SMS Gora ({account['email']})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_RECIPIENTS: split_numbers(user_input.get(CONF_RECIPIENTS)),
                        CONF_DEVICE_ID: user_input.get(CONF_DEVICE_ID) or None,
                    },
                )
        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)
