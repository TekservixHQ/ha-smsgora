"""SMS Gora notify entity: sends to the recipients set up in the integration."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmsGoraConfigEntry
from .api import SmsGoraError
from .const import CONF_DEVICE_ID, CONF_RECIPIENTS, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: SmsGoraConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([SmsGoraNotifyEntity(entry)])


class SmsGoraNotifyEntity(NotifyEntity):
    """notify.send_message target that texts the default recipients."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: SmsGoraConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SMS Gora",
            manufacturer="Tekservix",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://tekservix.com/smsgora/app/",
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        recipients = self._entry.data.get(CONF_RECIPIENTS) or []
        if not recipients:
            raise HomeAssistantError("SMS Gora: add default recipients in the integration, or use the smsgora.send_sms action")
        text = f"{title}\n{message}" if title else message
        try:
            await self._entry.runtime_data.send_sms(recipients, text, device_id=self._entry.data.get(CONF_DEVICE_ID))
        except SmsGoraError as err:
            raise HomeAssistantError(f"SMS Gora: {err}") from err
