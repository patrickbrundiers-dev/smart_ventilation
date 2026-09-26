from __future__ import annotations

import math
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import *


def _float_state(hass, entity_id):
    state = hass.states.get(entity_id)
    if state is None:
        return None
    try:
        value = float(state.state)
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    return None


def _is_on(hass, entity_id):
    state = hass.states.get(entity_id)
    return state is not None and state.state in ("on", "open", "true", "1")


def _is_raining(hass, entity_id):
    """Binary-Sensor (on) ODER numerischer Regensensor (z. B. mm/h > 0)."""
    if _is_on(hass, entity_id):
        return True
    value = _float_state(hass, entity_id)
    return value is not None and value > 0


def _angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def _wind_kmh(hass, entity_id):
    state = hass.states.get(entity_id)
    value = _float_state(hass, entity_id)
    if value is None:
        return None
    unit = state.attributes.get("unit_of_measurement", "") if state else ""
    return value * 3.6 if unit in ("m/s", "mps") else value


def _relative_humidity_from_absolute(absolute_humidity, temperature_c):
    """Approximate RH from absolute humidity in g/m³ and temperature in °C."""
    if absolute_humidity is None or temperature_c is None:
        return None
    tk = temperature_c + 273.15
    vapor_pressure = absolute_humidity * tk / 216.7
    saturation = 6.112 * math.exp((17.62 * temperature_c) / (243.12 + temperature_c))
    if saturation <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * vapor_pressure / saturation))


def _dew_point(temperature_c, rh):
    if temperature_c is None or rh is None or rh <= 0:
        return None
    gamma = math.log(rh / 100.0) + (17.62 * temperature_c) / (243.12 + temperature_c)
    return (243.12 * gamma) / (17.62 - gamma)


class SmartVentilationCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        # Optionen überschreiben die Ersteinrichtung
        self.data = {**entry.data, **entry.options}
        self._remove_listener = None
        self._feedback_remove = None
        self._target_notified = False
        self._session_start_diff = None

        self.store = Store(
            hass, STORE_VERSION,
            f"{STORE_KEY}_{entry.entry_id}",
        )

        self.learned_ach = 8.0
        self.samples = 0
        self.models = {}
        self.session = None

        self.recommendation = "Keine Lüftung erforderlich"
        self.recommended_minutes = 0
        self.recommended_mode = "Keine Lüftung"
        self.block_reason = ""
        self.last_notification_key = None
        self.last_notification_at = None
        self._listeners = []
        self.stats = {}
        self._auto_season = None

    # ------------------------------------------------------------------
    # Statistik
    # ------------------------------------------------------------------
    @staticmethod
    def _period_keys(now):
        iso = now.isocalendar()
        return {
            "day": now.strftime("%Y-%m-%d"),
            "week": f"{iso[0]}-W{iso[1]:02d}",
            "month": now.strftime("%Y-%m"),
            "total": "total",
        }

    @staticmethod
    def _empty_period(key):
        return {"key": key, "count": 0, "ok": 0, "short": 0, "seconds": 0.0}

    def _roll_periods(self):
        """Setzt Tag/Woche/Monat zurück, wenn ein neuer Zeitraum begonnen hat."""
        changed = False
        for period, key in self._period_keys(dt_util.now()).items():
            if self.stats.get(period, {}).get("key") != key:
                self.stats[period] = self._empty_period(key)
                changed = True
        self.stats.setdefault("max_seconds", 0.0)
        return changed

    def period_stats(self, period):
        self._roll_periods()
        p = self.stats[period]
        count = p["count"]
        return {
            "count": count,
            "ok": p["ok"],
            "short": p["short"],
            "minutes": round(p["seconds"] / 60, 1),
            "avg_minutes": round(p["seconds"] / count / 60, 1) if count else 0.0,
        }

    @property
    def ventilated_today(self):
        self._roll_periods()
        return self.stats["day"]["ok"] > 0

    @property
    def max_duration_minutes(self):
        return round(self.stats.get("max_seconds", 0.0) / 60, 1)

    @property
    def current_duration_seconds(self):
        if not self.session:
            return 0
        return int((dt_util.now() - self.session["started"]).total_seconds())

    @callback
    def async_add_listener(self, update_callback):
        self._listeners.append(update_callback)

        @callback
        def remove():
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)
        return remove

    @callback
    def _notify_listeners(self):
        for update_callback in list(self._listeners):
            update_callback()

    async def async_setup(self):
        stored = await self.store.async_load() or {}
        self.learned_ach = float(stored.get("learned_ach", 8.0))
        self.samples = int(stored.get("samples", 0))
        self.models = stored.get("models", {})
        self.stats = stored.get("stats", {})
        self._roll_periods()

        entities = [
            self.data[CONF_WINDOW],
            self.data[CONF_INDOOR_HUMIDITY],
            self.data[CONF_OUTDOOR_HUMIDITY],
            self.data[CONF_INDOOR_TEMP],
            self.data[CONF_OUTDOOR_TEMP],
            self.data[CONF_WIND_SPEED],
            self.data[CONF_WIND_DIRECTION],
            self.data[CONF_RAIN],
        ]
        if self.data.get(CONF_USE_SUN, True):
            entities.append(self.data.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY))

        self._remove_listener = async_track_state_change_event(
            self.hass, entities, self._state_changed
        )
        # Reihenfolge laut HA-API: (hass, action, interval)
        self._feedback_remove = async_track_time_interval(
            self.hass, self._feedback_tick, timedelta(seconds=30)
        )
        self._update_recommendation()

    async def _save(self):
        await self.store.async_save({
            "learned_ach": self.learned_ach,
            "samples": self.samples,
            "models": self.models,
            "stats": self.stats,
        })

    def async_unload(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._feedback_remove:
            self._feedback_remove()
            self._feedback_remove = None

    @callback
    def _state_changed(self, event):
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")

        if entity_id == self.data[CONF_WINDOW]:
            # Attribut-Änderungen (z. B. Batterie) dürfen die Lüftung nicht neu starten
            if new_state and new_state.state in ("on", "open", "true", "1"):
                if not self.session:
                    self._start_session()
            elif new_state and new_state.state in ("off", "closed", "false", "0"):
                if self.session:
                    self.hass.async_create_task(self._finish_session())

        self._update_recommendation()
        self._notify_listeners()

    def _context(self):
        wind = _wind_kmh(self.hass, self.data[CONF_WIND_SPEED])
        wind_dir = _float_state(self.hass, self.data[CONF_WIND_DIRECTION])
        indoor_t = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        outdoor_t = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])

        angle = None
        if wind_dir is not None:
            source_dir = (
                wind_dir
                if self.data.get(CONF_WIND_IS_FROM, True)
                else (wind_dir + 180) % 360
            )
            angle = _angle_diff(
                float(self.data[CONF_WINDOW_DIRECTION]), source_dir
            )

        temp_diff = (
            abs(indoor_t - outdoor_t)
            if indoor_t is not None and outdoor_t is not None
            else None
        )

        return wind, angle, temp_diff

    def _bucket(self, wind, angle, temp_diff):
        if wind is None:
            wb = "unknown"
        elif wind < 5:
            wb = "0-5"
        elif wind < 15:
            wb = "5-15"
        elif wind < 30:
            wb = "15-30"
        else:
            wb = "30+"

        if angle is None:
            ab = "unknown"
        elif angle <= 30:
            ab = "0-30"
        elif angle <= 60:
            ab = "30-60"
        else:
            ab = "60+"

        if temp_diff is None:
            tb = "unknown"
        elif temp_diff < 5:
            tb = "0-5"
        elif temp_diff < 10:
            tb = "5-10"
        else:
            tb = "10+"

        return f"wind:{wb}|angle:{ab}|temp:{tb}"

    def _model_ach(self, wind, angle, temp_diff):
        key = self._bucket(wind, angle, temp_diff)
        model = self.models.get(key)
        if model and model.get("samples", 0) >= 2:
            return max(0.5, float(model["ach"])), key
        return max(0.5, self.learned_ach), key

    def _start_session(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        diff = (indoor - outdoor) if indoor is not None and outdoor is not None else None

        wind, angle, temp_diff = self._context()

        # Jede Öffnung wird gezählt; gelernt wird nur, wenn innen feuchter war als außen
        self.session = {
            "started": dt_util.now(),
            "initial_diff": diff,
            "wind": wind,
            "angle": angle,
            "temp_diff": temp_diff,
            "target_reached": False,
        }
        self._session_start_diff = diff
        self._target_notified = False

    def _target_reached_now(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        if indoor is None or outdoor is None:
            return False, None
        current_diff = indoor - outdoor
        target_abs = float(self.data.get(CONF_TARGET_ABS, DEFAULT_TARGET_ABS))
        # Ziel: Feuchteunterschied fast ausgeglichen ODER innen unter Zielwert
        reached = current_diff <= DEFAULT_TARGET_DIFF or indoor <= target_abs
        return reached, current_diff

    async def _feedback_tick(self, _now=None):
        if self._roll_periods():
            await self._save()
        self._update_recommendation()
        self._notify_listeners()
        if not self.session:
            return
        if not _is_on(self.hass, self.data[CONF_WINDOW]):
            return

        reached, current_diff = self._target_reached_now()
        if not reached:
            return
        self.session["target_reached"] = True

        if self._target_notified:
            return
        self._target_notified = True

        minutes = max(1, round(self.current_duration_seconds / 60))
        await self._send(
            f"Lüften fertig: {self.data[CONF_NAME]}",
            (
                f"Das Lüftungsziel ist erreicht. "
                f"Feuchteunterschied nur noch {current_diff:.1f} g/m³. "
                f"Gelüftet seit ca. {minutes} Minuten. Fenster kann zu."
            ),
            f"smart_ventilation_{self.entry.entry_id}",
        )

    @property
    def notify_targets(self):
        """Gewählte notify-Dienste; ältere Einträge nutzen noch das Textfeld."""
        targets = self.data.get(CONF_NOTIFY_SERVICES)
        if targets is None:
            legacy = (self.data.get(CONF_NOTIFY_SERVICE) or "").strip()
            targets = [legacy] if legacy else []
        return [t for t in targets if isinstance(t, str) and t.startswith("notify.")]

    async def _send(self, title, message, tag):
        """An alle gewählten Empfänger senden; ein fehlerhafter Dienst stoppt die anderen nicht."""
        sent = False
        for target in self.notify_targets:
            service_name = target.partition(".")[2]
            if not self.hass.services.has_service("notify", service_name):
                continue
            try:
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {"title": title, "message": message, "data": {"tag": tag}},
                    blocking=False,
                )
                sent = True
            except Exception:  # noqa: BLE001 – ein Handy offline darf nichts blockieren
                continue
        return sent

    def _record_stats(self, elapsed, success):
        self._roll_periods()
        for period in ("day", "week", "month", "total"):
            p = self.stats[period]
            p["count"] += 1
            p["seconds"] += elapsed
            if success:
                p["ok"] += 1
            else:
                p["short"] += 1
        self.stats["max_seconds"] = max(self.stats.get("max_seconds", 0.0), elapsed)

    async def _finish_session(self):
        if not self.session:
            return

        session = self.session
        self.session = None
        self._session_start_diff = None

        elapsed = (dt_util.now() - session["started"]).total_seconds()

        # Kurzes Auf/Zu (< 30 s) zählt nicht als Lüftung
        if elapsed >= 30:
            reached, _ = self._target_reached_now()
            success = (
                elapsed >= DEFAULT_MIN_SESSION
                and (session["target_reached"] or reached)
            )
            self._record_stats(elapsed, success)
            await self._save()
        self._notify_listeners()

        if elapsed < DEFAULT_MIN_SESSION or elapsed > DEFAULT_MAX_SESSION:
            return

        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        initial_diff = session["initial_diff"]
        if indoor is None or outdoor is None or initial_diff is None:
            return

        raw_final = indoor - outdoor
        # Bis unter Außenniveau gelüftet: nicht verwerfen, sondern konservativ begrenzen
        final_diff = max(raw_final, MIN_FINAL_DIFF)

        if initial_diff <= MIN_FINAL_DIFF or final_diff >= initial_diff:
            return

        duration_min = elapsed / 60
        reduction = max(0.0, 1 - (raw_final / initial_diff))
        status = "Ziel erreicht" if raw_final <= DEFAULT_TARGET_DIFF else "vor Ziel beendet"
        await self._send(
            f"Lüftung abgeschlossen: {self.data[CONF_NAME]}",
            (
                f"{status}. Dauer: {duration_min:.1f} Minuten. "
                f"Feuchteunterschied: {initial_diff:.1f} → "
                f"{raw_final:.1f} g/m³ ({min(reduction, 1) * 100:.0f}% reduziert)."
            ),
            f"smart_ventilation_{self.entry.entry_id}_result",
        )

        if _is_raining(self.hass, self.data[CONF_RAIN]):
            return

        # Luftwechsel pro STUNDE (elapsed in Sekunden)
        ach = -(3600 / elapsed) * math.log(final_diff / initial_diff)
        if not 0.2 <= ach <= 40:
            return

        self.learned_ach = self.learned_ach * 0.8 + ach * 0.2
        self.samples += 1

        key = self._bucket(
            session["wind"], session["angle"], session["temp_diff"]
        )
        old = self.models.get(key, {"ach": self.learned_ach, "samples": 0})
        count = int(old.get("samples", 0))
        old_ach = float(old.get("ach", ach))
        new_ach = old_ach * 0.8 + ach * 0.2 if count else ach

        self.models[key] = {
            "ach": new_ach,
            "samples": count + 1,
            "last_observed_ach": ach,
        }

        await self._save()
        self._notify_listeners()

    @property
    def season(self):
        """'summer' oder 'winter' – manuell gesetzt oder automatisch per Außentemperatur."""
        mode = self.data.get(CONF_SEASON_MODE, DEFAULT_SEASON_MODE)
        if mode in (SEASON_SUMMER, SEASON_WINTER):
            return mode

        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        threshold = float(self.data.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD))
        if outdoor is None:
            return self._auto_season or SEASON_WINTER
        # Hysterese: erst deutlich über/unter der Schwelle umschalten
        if outdoor < threshold - SEASON_HYSTERESIS:
            self._auto_season = SEASON_WINTER
        elif outdoor > threshold + SEASON_HYSTERESIS:
            self._auto_season = SEASON_SUMMER
        elif self._auto_season is None:
            self._auto_season = SEASON_WINTER if outdoor < threshold else SEASON_SUMMER
        return self._auto_season

    def _temperature_block(self):
        """Winter: nie sperren (Stoßlüften). Sommer: sperren, wenn draußen deutlich wärmer."""
        if self.season == SEASON_WINTER:
            return False, ""

        indoor = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if indoor is None or outdoor is None:
            return False, ""

        warmer = outdoor - indoor
        maximum = float(self.data.get(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF))
        if warmer > maximum:
            return True, f"Draußen {warmer:.1f} °C wärmer als drinnen"
        return False, ""

    def _winter_max_minutes(self):
        """Stoßlüften: je kälter, desto kürzer (Richtwerte Verbraucherzentrale)."""
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if outdoor is None or outdoor < 5:
            return 5
        if outdoor < 10:
            return 10
        return 15

    def _sun_info(self):
        if not self.data.get(CONF_USE_SUN, True):
            return None

        state = self.hass.states.get(
            self.data.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        )
        if state is None:
            return None

        try:
            elevation = float(state.attributes.get("elevation", 0))
            azimuth = float(state.attributes.get("azimuth", 0))
        except (TypeError, ValueError):
            return None

        return elevation, azimuth

    def _sun_effect(self):
        info = self._sun_info()
        if info is None:
            return False, False, ""

        elevation, azimuth = info
        minimum = float(
            self.data.get(CONF_MIN_SUN_ELEVATION, DEFAULT_MIN_SUN_ELEVATION)
        )

        if elevation < minimum:
            return False, False, ""

        angle = _angle_diff(
            float(self.data[CONF_WINDOW_DIRECTION]), azimuth
        )

        if angle <= 35:
            return True, True, (
                f"Direkte Sonne am Fenster "
                f"(Azimut {azimuth:.0f}°, Höhe {elevation:.0f}°)"
            )

        return True, False, ""

    def _notification_key(self):
        if self.recommended_minutes <= 0:
            return None
        return f"{self.recommended_mode}|{self.block_reason}"

    async def _send_notification_if_needed(self):
        if not self.notify_targets or self.recommended_minutes <= 0:
            return

        if self.block_reason and "Sonne" not in self.block_reason:
            return

        # Nicht erinnern, während bereits gelüftet wird
        if self.session or _is_on(self.hass, self.data[CONF_WINDOW]):
            return

        key = self._notification_key()
        if key is None:
            return

        now = dt_util.now()
        cooldown_s = int(
            self.data.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
        ) * 60

        # Cooldown gilt global, nicht nur pro identischer Meldung
        if (
            self.last_notification_at is not None
            and (now - self.last_notification_at).total_seconds() < cooldown_s
        ):
            return

        sent = await self._send(
            f"Lüften: {self.data[CONF_NAME]}",
            (
                f"Jetzt wäre ein guter Zeitpunkt zum Lüften – "
                f"{self.recommended_mode}, voraussichtlich "
                f"{self.recommended_minutes} Minuten."
            ),
            f"smart_ventilation_{self.entry.entry_id}",
        )
        if sent:
            self.last_notification_key = key
            self.last_notification_at = now

    def _update_recommendation(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])

        self.block_reason = ""

        if indoor is None or outdoor is None:
            self.recommendation = "Sensordaten fehlen"
            self.recommended_minutes = 0
            return

        diff = indoor - outdoor

        if diff <= DEFAULT_TARGET_DIFF:
            self.recommendation = "Keine Lüftung erforderlich"
            self.recommended_minutes = 0
            self.recommended_mode = "Keine Lüftung"
            return

        if _is_raining(self.hass, self.data[CONF_RAIN]):
            self.recommendation = "Nicht lüften – Regen"
            self.recommended_minutes = 0
            self.recommended_mode = "Geschlossen"
            self.block_reason = "Regen"
            return

        temp_block, temp_reason = self._temperature_block()
        if temp_block:
            self.recommendation = "Nicht lüften – draußen zu warm"
            self.recommended_minutes = 0
            self.recommended_mode = "Geschlossen"
            self.block_reason = temp_reason
            return

        sun_active, direct_sun, sun_reason = self._sun_effect()

        wind, angle, temp_diff = self._context()
        effective_ach, bucket = self._model_ach(wind, angle, temp_diff)

        if wind is not None:
            effective_ach *= 1 + min(wind / 60, 0.5)
            if angle is not None:
                if angle <= 30:
                    effective_ach *= 1.25
                elif angle <= 60:
                    effective_ach *= 1.10
                else:
                    effective_ach *= 0.9

        ratio = DEFAULT_TARGET_DIFF / max(diff, DEFAULT_TARGET_DIFF + 0.01)
        minutes = -60 / effective_ach * math.log(ratio)
        minutes = max(2, min(60, minutes))

        if self.season == SEASON_WINTER:
            # Winter: nie kippen (kühlt Wände aus), kurz und komplett öffnen
            minutes = min(minutes, self._winter_max_minutes())
            mode = "Stoßlüften"
        elif direct_sun:
            minutes = min(minutes, 5)
            mode = "Kurz komplett öffnen"
            self.block_reason = sun_reason
        elif minutes <= 12 and (wind is None or wind >= 5):
            mode = "Komplett öffnen"
        else:
            mode = "Kippfenster"

        self.recommended_minutes = round(minutes)
        self.recommended_mode = mode
        self.recommendation = f"{mode} – ca. {self.recommended_minutes} Min."
        self.hass.async_create_task(self._send_notification_if_needed())

    @property
    def humidity_difference(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        if indoor is None or outdoor is None:
            return None
        return round(indoor - outdoor, 2)

    @property
    def temperature_difference(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if indoor is None or outdoor is None:
            return None
        return round(abs(indoor - outdoor), 1)

    @property
    def indoor_rh(self):
        ah = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        return _relative_humidity_from_absolute(ah, temp)

    @property
    def outdoor_rh(self):
        ah = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        temp = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        return _relative_humidity_from_absolute(ah, temp)

    @property
    def indoor_dew_point(self):
        temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        return _dew_point(temp, self.indoor_rh)

    @property
    def outdoor_dew_point(self):
        temp = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        return _dew_point(temp, self.outdoor_rh)

    @property
    def mold_risk(self):
        rh = self.indoor_rh
        dp = self.indoor_dew_point
        temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])

        if rh is None or dp is None or temp is None:
            return "unbekannt"

        # Air-only estimate: not a building-material surface model.
        if rh >= 75 or (temp - dp) <= 3:
            return "hoch"
        if rh >= 65 or (temp - dp) <= 5:
            return "erhöht"
        return "niedrig"

    @property
    def sun_data(self):
        info = self._sun_info()
        if info is None:
            return None
        return {"elevation": info[0], "azimuth": info[1]}

    @property
    def context_model(self):
        wind, angle, temp_diff = self._context()
        ach, key = self._model_ach(wind, angle, temp_diff)
        return {"ach": round(ach, 2), "bucket": key}
