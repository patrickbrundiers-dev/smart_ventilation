from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VentilatedTodaySensor(coordinator),
        VentilationRecommendedSensor(coordinator),
    ])


class BaseBinary(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class VentilatedTodaySensor(BaseBinary):
    """An, sobald heute mindestens eine erfolgreiche Lüftung stattfand."""
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, c): super().__init__(c, "ventilated_today", "Heute gelüftet")

    @property
    def is_on(self):
        return self.coordinator.ventilated_today


class VentilationRecommendedSensor(BaseBinary):
    """An, wenn jetzt gelüftet werden sollte – ideal als Automations-Trigger."""
    _attr_icon = "mdi:air-filter"

    def __init__(self, c): super().__init__(c, "recommended", "Lüften empfohlen")

    @property
    def is_on(self):
        return self.coordinator.recommended_minutes > 0

    @property
    def extra_state_attributes(self):
        return {
            "modus": self.coordinator.recommended_mode,
            "dauer_min": self.coordinator.recommended_minutes,
            "grund_blockiert": self.coordinator.block_reason,
        }
