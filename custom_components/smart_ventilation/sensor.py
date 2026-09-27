from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import SmartVentilationCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if getattr(coordinator, "is_overview", False):
        async_add_entities([
            MostUrgentRoomSensor(coordinator),
            RoomsNeedingSensor(coordinator),
        ])
        return
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
        SeasonSensor(coordinator),
        BestTimeSensor(coordinator),
        WallTemperatureSensor(coordinator),
        WallHumiditySensor(coordinator),
        AirQualitySensor(coordinator),
        HeatLossTodaySensor(coordinator),
        EnergyTotalSensor(coordinator),
        CostMonthSensor(coordinator),
        PreheatSavingsMonthSensor(coordinator),
        MoldStreakSensor(coordinator),
        NeedMonthSensor(coordinator),
    ])


class BaseSensor(SensorEntity):
    # Push statt Polling: Coordinator meldet Änderungen aktiv
    _attr_should_poll = False
    # Entity-IDs bekommen den Raumnamen als Präfix -> keine _2/_3-Kollisionen
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        # Name kommt aus translations/<sprache>.json (entity.sensor.<key>.name)
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.data["name"],
            manufacturer="Custom",
            model="Adaptive Ventilation",
            sw_version="2.8.0",
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
    # Kartendaten nicht in der Datenbank speichern
    _unrecorded_attributes = frozenset({"karte"})

    def __init__(self, c): super().__init__(c, "recommendation", "Empfehlung")
    @property
    def native_value(self): return self.coordinator.recommendation

    @property
    def extra_state_attributes(self):
        return {
            **super().extra_state_attributes,
            "grund": self.coordinator.recommend_reason,
            "karte": self.coordinator.card_data(),
        }


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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_options = ["low", "elevated", "high", "unknown"]
    def __init__(self, c): super().__init__(c, "mold_risk", "Schimmelrisiko")
    @property
    def native_value(self):
        return {"niedrig": "low", "erhöht": "elevated", "hoch": "high"}.get(self.coordinator.mold_risk, "unknown")


class NotificationStatusSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, c):
        super().__init__(c, "notification_status", "Benachrichtigung")

    @property
    def extra_state_attributes(self):
        return {"empfaenger": self.coordinator.notify_targets}

    @property
    def native_value(self):
        if not self.coordinator.notify_targets:
            return "Nicht konfiguriert"
        if self.coordinator.recommended_minutes > 0:
            return "Lüften empfohlen"
        return "Keine Benachrichtigung"


class VentilationRunningSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["running", "idle"]
    def __init__(self, c):
        super().__init__(c, "ventilation_running", "Lüftung läuft")

    @property
    def native_value(self):
        return "running" if self.coordinator.session else "idle"

    @property
    def extra_state_attributes(self):
        session = self.coordinator.session or {}
        return {
            "offene_fenster": self.coordinator.open_windows(),
            "querlueften": bool(session.get("cross")),
            "heizung_abgesenkt": list((session.get("heating") or {}).keys()),
            "heizung_selbst_geregelt": session.get("heating_external") or {},
        }


class VentilationProgressSensor(BaseSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c):
        super().__init__(c, "ventilation_progress", "Lüftungsfortschritt")

    @property
    def native_value(self):
        return self.coordinator.progress

    @property
    def native_unit_of_measurement(self):
        return "%"


class ACHSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "learned_ach", "Gelernter Luftwechsel")
    @property
    def native_value(self): return round(self.coordinator.learned_ach, 2)
    @property
    def native_unit_of_measurement(self): return "1/h"


class SamplesSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, c): super().__init__(c, "learning_samples", "Lernvorgänge")
    @property
    def native_value(self): return self.coordinator.samples


class ModelSamplesSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, c): super().__init__(c, "context_model_ach", "Kontext-Luftwechsel")
    @property
    def native_value(self): return self.coordinator.context_model["ach"]
    @property
    def native_unit_of_measurement(self): return "1/h"


class SunElevationSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, c): super().__init__(c, "sun_elevation", "Sonnenhöhe")
    @property
    def native_value(self):
        data = self.coordinator.sun_data
        try: return round(float(data["elevation"]), 1) if data else None
        except (TypeError, ValueError): return None
    @property
    def native_unit_of_measurement(self): return "°"


class SunAzimuthSensor(BaseSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
            "waermeverlust_kwh": st["kwh"],
            "kosten_eur": st["cost"],
            "vorheiz_ersparnis_kwh": st["kwh_gespart"],
            "vorheiz_ersparnis_eur": st["kosten_gespart"],
        }


class CurrentDurationSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, c): super().__init__(c, "current_duration", "Aktuelle Lüftungsdauer")
    @property
    def native_value(self): return self.coordinator.current_duration_seconds
    @property
    def native_unit_of_measurement(self): return "s"


class MaxDurationSensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, c): super().__init__(c, "max_duration", "Längste Lüftung")
    @property
    def native_value(self): return self.coordinator.max_duration_minutes
    @property
    def native_unit_of_measurement(self): return "min"


class SeasonSensor(BaseSensor):
    """Aktiver Modus: Sommer oder Winter."""
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["summer", "winter"]

    def __init__(self, c): super().__init__(c, "season", "Jahreszeit-Modus")

    @property
    def native_value(self):
        return "winter" if self.coordinator.season == "winter" else "summer"


    @property
    def extra_state_attributes(self):
        mode = self.coordinator.data.get("season_mode", "auto")
        return {"einstellung": {"auto": "Automatisch", "summer": "Sommer", "winter": "Winter"}.get(mode, mode)}


class BestTimeSensor(BaseSensor):
    """Bester Lüftungszeitpunkt der nächsten 24 h (Zeitstempel -> 'in 3 Stunden')."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, c): super().__init__(c, "best_time", "Bester Lüftungszeitpunkt")

    @property
    def native_value(self):
        return self.coordinator.best_time

    @property
    def extra_state_attributes(self):
        info = {k: v for k, v in self.coordinator.best_info.items() if k != "ok"}
        return {"text": self.coordinator.best_reason, **info}


class WallTemperatureSensor(BaseSensor):
    """Geschätzte Temperatur an der kältesten Wandstelle (Außenecke, hinter Möbeln)."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c): super().__init__(c, "wall_temperature", "Wandtemperatur (geschätzt)")
    @property
    def native_value(self):
        v = self.coordinator.wall_temperature
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "°C"


class WallHumiditySensor(BaseSensor):
    """Relative Feuchte an der kalten Wand – ab 80 % droht Schimmel (DIN 4108-2)."""
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c): super().__init__(c, "wall_humidity", "Feuchte an der Wand")
    @property
    def native_value(self):
        v = self.coordinator.wall_rh
        return round(v, 1) if v is not None else None
    @property
    def native_unit_of_measurement(self): return "%"


class AirQualitySensor(BaseSensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["good", "moderate", "poor"]

    def __init__(self, c): super().__init__(c, "air_quality", "Luftqualität")
    @property
    def available(self): return bool(self.coordinator.data.get("co2_sensor"))
    @property
    def native_value(self):
        return {"gut": "good", "mäßig": "moderate", "schlecht": "poor"}.get(self.coordinator.air_quality)


class HeatLossTodaySensor(BaseSensor):
    """Geschätzter Wärmeverlust durch Lüften heute."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, c): super().__init__(c, "heat_loss_today", "Wärmeverlust Lüften heute")
    @property
    def native_value(self): return self.coordinator.period_stats("day")["kwh"]
    @property
    def native_unit_of_measurement(self): return "kWh"


class EnergyTotalSensor(BaseSensor):
    """Gesamter Wärmeverlust durch Lüften seit der Einrichtung – wächst nie zurück (im
    Gegensatz zu „heute"/„Monat") und eignet sich deshalb als Verbrauchssensor fürs
    Home-Assistant-Energie-Dashboard (dort unter „Individuelle Geräte" hinzufügen)."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, c): super().__init__(c, "energy_total", "Lüftungsenergie gesamt")
    @property
    def native_value(self): return self.coordinator.period_stats("total")["kwh"]
    @property
    def native_unit_of_measurement(self): return "kWh"


class CostMonthSensor(BaseSensor):
    """Geschätzte Heizkosten durch Lüften im laufenden Monat."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, c): super().__init__(c, "cost_month", "Lüftungskosten Monat")
    @property
    def native_value(self): return self.coordinator.period_stats("month")["cost"]
    @property
    def native_unit_of_measurement(self): return "EUR"


class PreheatSavingsMonthSensor(BaseSensor):
    """Geschätzte Heizkosten-Ersparnis durchs Vorheizen im laufenden Monat."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, c): super().__init__(c, "preheat_savings_month", "Vorheiz-Ersparnis Monat")
    @property
    def native_value(self): return self.coordinator.period_stats("month")["kosten_gespart"]
    @property
    def native_unit_of_measurement(self): return "EUR"


# ----------------------------------------------------------------------
# Übersicht über alle Räume
# ----------------------------------------------------------------------
class OverviewBase(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.data.get("name", "Lüften Übersicht"),
            manufacturer="Custom",
            model="Adaptive Ventilation – Übersicht",
            sw_version="2.8.0",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def extra_state_attributes(self):
        return {
            "raeume": self.coordinator.room_list(),
            "summe": self.coordinator.totals(),
            "trend_tage": self.coordinator.day_trend(7),
        }


class MostUrgentRoomSensor(OverviewBase):

    def __init__(self, c): super().__init__(c, "most_urgent", "Dringendster Raum")
    @property
    def native_value(self): return self.coordinator.most_urgent


class RoomsNeedingSensor(OverviewBase):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c): super().__init__(c, "rooms_needing", "Räume mit Lüftungsbedarf")
    @property
    def native_value(self): return len(self.coordinator.rooms_needing())
    @property
    def native_unit_of_measurement(self): return "Räume"


class MoldStreakSensor(BaseSensor):
    """Kritische Tage in Folge (Wand ≥ 6 h/Tag über 80 % Feuchte)."""
    _unrecorded_attributes = frozenset({"letzte_14_tage_h"})
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, c): super().__init__(c, "mold_streak", "Kritische Schimmeltage in Folge")
    @property
    def native_value(self): return self.coordinator.mold_streak()[0]
    @property
    def native_unit_of_measurement(self): return "d"
    @property
    def extra_state_attributes(self):
        log = self.coordinator.mold_log
        return {
            "stunden_heute": self.coordinator.mold_hours_today,
            "letzte_14_tage_h": {d: round(m / 60, 1) for d, m in sorted(log.items())[-14:]},
        }


class NeedMonthSensor(BaseSensor):
    """Stunden mit Lüftungsbedarf im laufenden Monat, Attribute: Vergleich des letzten Monats."""
    _unrecorded_attributes = frozenset({"verlauf", "letzter_monat"})
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, c): super().__init__(c, "need_month", "Lüftungsbedarf diesen Monat")
    @property
    def native_value(self): return self.coordinator.period_stats("month")["need_hours"]
    @property
    def native_unit_of_measurement(self): return "h"
    @property
    def extra_state_attributes(self):
        return {
            "letzter_monat": self.coordinator.month_comparison(),
            "verlauf": self.coordinator.history,
        }
