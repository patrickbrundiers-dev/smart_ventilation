from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import SmartVentilationCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        RecommendationSensor(coordinator),
        MinutesSensor(coordinator),
        HumidityDifferenceSensor(coordinator),
        TemperatureDifferenceSensor(coordinator),
        IndoorRHSensor(coordinator),
        OutdoorRHSensor(coordinator),
        IndoorDewPointSensor(coordinator),
        OutdoorDewPointSensor(coordinator),
        MoldRiskSensor(coordinator),
        NotificationStatusSensor(coordinator),
        VentilationRunningSensor(coordinator),
        VentilationProgressSensor(coordinator),
        ACHSensor(coordinator),
        SamplesSensor(coordinator),
        ModelSamplesSensor(coordinator),
        SunElevationSensor(coordinator),
        SunAzimuthSensor(coordinator),
        PeriodSensor(coordinator, "day", "Lüftungen heute"),
        PeriodSensor(coordinator, "week", "Lüftungen Woche"),
        PeriodSensor(coordinator, "month", "Lüftungen Monat"),
        PeriodSensor(coordinator, "total", "Lüftungen gesamt"),
        CurrentDurationSensor(coordinator),
        MaxDurationSensor(coordinator),
    ])


class BaseSensor(SensorEntity):
    # Push statt Polling: Coordinator meldet Änderungen aktiv
    _attr_should_poll = False
    # Entity-IDs bekommen den Raumnamen als Präfix -> keine _2/_3-Kollisionen
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.data["name"],
            manufacturer="Custom",
            model="Adaptive Ventilation",
            sw_version="1.6.1",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def extra_state_attributes(self):
        model = self.coordinator.context_model
        return {
            "room_volume_m3": self.coordinator.data["volume"],
            "window_direction_deg": self.coordinator.data["window_direction"],
            "max_temperature_difference_c": self.coordinator.data.get("max_temperature_difference"),
            "sun_integration": self.coordinator.data.get("use_sun", True),
            "learning_samples": self.coordinator.samples,
            "learned_ach_general": round(self.coordinator.learned_ach, 2),
            "context_model_ach": model["ach"],
            "context_model_bucket": model["bucket"],
            "block_reason": self.coordinator.block_reason,
        }


class RecommendationSensor(BaseSensor):
    def __init__(self, c): super().__init__(c, "recommendation", "Empfehlung")
    @property
    def native_value(self): return self.coordinator.recommendation


class MinutesSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DURATION
    def __init__(self, c): super().__init__(c, "minutes", "Empfohlene Dauer")
    @property
    def native_value(self): return self.coordinator.recommended_minutes
    @property
    def native_unit_of_measurement(self): return "min"


class HumidityDifferenceSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "humidity_difference", "Feuchteunterschied")
    @property
    def native_value(self): return self.coordinator.humidity_difference
    @property
    def native_unit_of_measurement(self): return "g/m³"


class TemperatureDifferenceSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "temperature_difference", "Temperaturdifferenz")
    @property
    def native_value(self): return self.coordinator.temperature_difference
    @property
    def native_unit_of_measurement(self): return "°C"


class IndoorRHSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.HUMIDITY
    def __init__(self, c): super().__init__(c, "indoor_rh", "Berechnete Raumfeuchte")
    @property
    def native_value(self):
        v = self.coordinator.indoor_rh
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "%"


class OutdoorRHSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.HUMIDITY
    def __init__(self, c): super().__init__(c, "outdoor_rh", "Berechnete Außenfeuchte")
    @property
    def native_value(self):
        v = self.coordinator.outdoor_rh
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "%"


class IndoorDewPointSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    def __init__(self, c): super().__init__(c, "indoor_dew_point", "Taupunkt innen")
    @property
    def native_value(self):
        v = self.coordinator.indoor_dew_point
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "°C"


class OutdoorDewPointSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    def __init__(self, c): super().__init__(c, "outdoor_dew_point", "Taupunkt außen")
    @property
    def native_value(self):
        v = self.coordinator.outdoor_dew_point
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "°C"


class MoldRiskSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["niedrig", "erhöht", "hoch", "unbekannt"]
    def __init__(self, c): super().__init__(c, "mold_risk", "Schimmelrisiko")
    @property
    def native_value(self): return self.coordinator.mold_risk


class NotificationStatusSensor(BaseSensor):
    def __init__(self, c):
        super().__init__(c, "notification_status", "Benachrichtigung")

    @property
    def native_value(self):
        if not self.coordinator.data.get("notify_service"):
            return "Nicht konfiguriert"
        if self.coordinator.recommended_minutes > 0:
            return "Lüften empfohlen"
        return "Keine Benachrichtigung"


class VentilationRunningSensor(BaseSensor):
    def __init__(self, c):
        super().__init__(c, "ventilation_running", "Lüftung läuft")

    @property
    def native_value(self):
        return "Läuft" if self.coordinator.session else "Aus"


class VentilationProgressSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c):
        super().__init__(c, "ventilation_progress", "Lüftungsfortschritt")

    @property
    def native_value(self):
        if not self.coordinator.session:
            return 0
        initial = self.coordinator.session.get("initial_diff")
        current = self.coordinator.humidity_difference
        if initial is None or current is None or initial <= 0:
            return 0
        progress = (1 - current / initial) * 100
        return round(max(0, min(100, progress)))

    @property
    def native_unit_of_measurement(self):
        return "%"


class ACHSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "learned_ach", "Gelernter Luftwechsel")
    @property
    def native_value(self): return round(self.coordinator.learned_ach, 2)
    @property
    def native_unit_of_measurement(self): return "1/h"


class SamplesSensor(BaseSensor):
    def __init__(self, c): super().__init__(c, "learning_samples", "Lernvorgänge")
    @property
    def native_value(self): return self.coordinator.samples


class ModelSamplesSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "context_model_ach", "Kontext-Luftwechsel")
    @property
    def native_value(self): return self.coordinator.context_model["ach"]
    @property
    def native_unit_of_measurement(self): return "1/h"


class SunElevationSensor(BaseSensor):
    def __init__(self, c): super().__init__(c, "sun_elevation", "Sonnenhöhe")
    @property
    def native_value(self):
        data = self.coordinator.sun_data
        try: return round(float(data["elevation"]), 1) if data else None
        except (TypeError, ValueError): return None
    @property
    def native_unit_of_measurement(self): return "°"


class SunAzimuthSensor(BaseSensor):
    def __init__(self, c): super().__init__(c, "sun_azimuth", "Sonnenrichtung")
    @property
    def native_value(self):
        data = self.coordinator.sun_data
        try: return round(float(data["azimuth"]), 1) if data else None
        except (TypeError, ValueError): return None
    @property
    def native_unit_of_measurement(self): return "°"


class PeriodSensor(BaseSensor):
    """Anzahl Lüftungen im Zeitraum; Details als Attribute."""
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, c, period, name):
        super().__init__(c, f"stats_{period}", name)
        self._period = period

    @property
    def native_value(self):
        return self.coordinator.period_stats(self._period)["count"]

    @property
    def native_unit_of_measurement(self):
        return "Lüftungen"

    @property
    def extra_state_attributes(self):
        st = self.coordinator.period_stats(self._period)
        return {
            "erfolgreich": st["ok"],
            "ohne_ziel": st["short"],
            "dauer_gesamt_min": st["minutes"],
            "dauer_durchschnitt_min": st["avg_minutes"],
        }


class CurrentDurationSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_icon = "mdi:timer-outline"

    def __init__(self, c): super().__init__(c, "current_duration", "Aktuelle Lüftungsdauer")
    @property
    def native_value(self): return self.coordinator.current_duration_seconds
    @property
    def native_unit_of_measurement(self): return "s"


class MaxDurationSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_icon = "mdi:timer-star-outline"

    def __init__(self, c): super().__init__(c, "max_duration", "Längste Lüftung")
    @property
    def native_value(self): return self.coordinator.max_duration_minutes
    @property
    def native_unit_of_measurement(self): return "min"
