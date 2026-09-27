from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VentilatedTodaySensor(coordinator),
        VentilationRecommendedSensor(coordinator),
        CoolingDownSensor(coordinator),
        QuietHoursSensor(coordinator),
        MoldAlarmSensor(coordinator),
        PartyModeSensor(coordinator),
    ])


class BaseBinary(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )


class VentilatedTodaySensor(BaseBinary):
    """An, sobald heute mindestens eine erfolgreiche Lüftung stattfand."""

    def __init__(self, c): super().__init__(c, "ventilated_today", "Heute gelüftet")

    @property
    def is_on(self):
        return self.coordinator.ventilated_today


class VentilationRecommendedSensor(BaseBinary):
    """An, wenn jetzt gelüftet werden sollte – ideal als Automations-Trigger."""

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


class CoolingDownSensor(BaseBinary):
    """An, wenn bei offenem Fenster die Auskühl-Grenze unterschritten ist."""
    _attr_device_class = BinarySensorDeviceClass.COLD

    def __init__(self, c): super().__init__(c, "cooling_down", "Raum kühlt aus")

    @property
    def is_on(self):
        return self.coordinator.cooling_down


class QuietHoursSensor(BaseBinary):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    """An während der Ruhezeit (keine Lüft-Erinnerungen)."""

    def __init__(self, c): super().__init__(c, "quiet_hours", "Ruhezeit")

    @property
    def is_on(self):
        return self.coordinator.in_quiet_hours()


class MoldAlarmSensor(BaseBinary):
    """An, wenn die Wand mehrere Tage in Folge kritisch feucht war."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, c): super().__init__(c, "mold_alarm", "Schimmelgefahr")

    @property
    def is_on(self):
        return self.coordinator.mold_alarm


class PartyModeSensor(BaseBinary):
    """An, während der Party-Modus läuft (per Button aktiviert, schaltet sich von selbst ab)."""
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, c): super().__init__(c, "party_mode", "Party-Modus")

    @property
    def is_on(self):
        return self.coordinator.party_active

    @property
    def extra_state_attributes(self):
        until = self.coordinator._party_until
        return {"aktiv_bis": until.isoformat() if self.coordinator.party_active and until else None}
