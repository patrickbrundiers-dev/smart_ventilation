from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        ResetLearningButton(coordinator),
        SnoozeButton(coordinator),
        SkipTodayButton(coordinator),
        PartyModeButton(coordinator),
    ])


class ResetLearningButton(ButtonEntity):
    """Verwirft den gelernten Luftwechsel; Statistik bleibt erhalten."""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_reset_learning"
        self._attr_translation_key = "reset_learning"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_press(self) -> None:
        await self.coordinator.async_reset_learning()


class SnoozeButton(ButtonEntity):
    """Erinnerung für 30 Minuten aussetzen – gleiche Wirkung wie der Button in der Push-Nachricht,
    aber auch direkt von der Dashboard-Karte aus nutzbar."""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_snooze"
        self._attr_translation_key = "snooze"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_press(self) -> None:
        await self.coordinator.async_snooze()


class SkipTodayButton(ButtonEntity):
    """Heute keine weiteren Erinnerungen mehr – siehe SnoozeButton."""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_skip_today"
        self._attr_translation_key = "skip_today"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_press(self) -> None:
        await self.coordinator.async_skip_today()


class PartyModeButton(ButtonEntity):
    """Für ein paar Stunden aggressiver lüften (z. B. bei Besuch); erneutes Drücken beendet ihn
    vorzeitig, sonst schaltet er sich nach PARTY_MODE_HOURS von selbst wieder ab."""
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_party_mode"
        self._attr_translation_key = "party_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
        )

    async def async_press(self) -> None:
        await self.coordinator.async_toggle_party_mode()
