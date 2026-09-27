from __future__ import annotations

import math
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import *
from . import notify_util
from .extras import RoomExtrasMixin
from .history import HistoryMixin


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
    return state is not None and state.state in ON_STATES





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


def _absolute_humidity(temperature_c, rh=None, dew_point=None):
    """Absolute Feuchte in g/m³ aus Taupunkt (bevorzugt) oder Temperatur + rel. Feuchte."""
    if temperature_c is None:
        return None
    if dew_point is not None:
        vapor = 6.112 * math.exp((17.62 * dew_point) / (243.12 + dew_point))
    elif rh is not None:
        vapor = rh / 100.0 * 6.112 * math.exp((17.62 * temperature_c) / (243.12 + temperature_c))
    else:
        return None
    return 216.7 * vapor / (273.15 + temperature_c)


def _num(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _dew_point(temperature_c, rh):
    if temperature_c is None or rh is None or rh <= 0:
        return None
    gamma = math.log(rh / 100.0) + (17.62 * temperature_c) / (243.12 + temperature_c)
    return (243.12 * gamma) / (17.62 - gamma)


class SmartVentilationCoordinator(RoomExtrasMixin, HistoryMixin):
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
        self.recommend_reason = ""
        self.block_reason = ""
        self.last_notification_key = None
        self.last_notification_at = None
        self._listeners = []
        self.stats = {}
        self._auto_season = None
        self._season_pending = None
        self._season_pending_since = None
        self.best_time = None
        self.best_info = {}
        self.best_reason = "Keine Wetter-Entität gewählt"
        self._forecast_checked = None
        self._action_remove = None
        self._snooze_until = None
        self._skip_date = None
        self._last_session_end = None
        self._humidity_active = False
        self._night_low = None       # läuft gerade mit (innerhalb des Nachtfensters)
        self._last_night_low = None  # zuletzt abgeschlossene Nacht - fürs Vorheizen
        self._unavailable_since = {}
        self.cool_plan = None
        self.preheat_plan_text = None
        self._rain_soon = False
        self._forecast_season = None
        self._init_extras()
        self._init_history()

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
                if period == "month" and self.stats.get("month"):
                    self._archive_month(self.stats["month"])
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
            "kwh": round(p.get("kwh", 0.0), 2),
            "need_hours": round(p.get("need_minutes", 0.0) / 60, 1),
            "cost": round(p.get("kwh", 0.0) * self.energy_price, 2),
            "kwh_gespart": round(p.get("kwh_gespart", 0.0), 2),
            "kosten_gespart": round(p.get("kwh_gespart", 0.0) * self.energy_price, 2),
        }

    @property
    def energy_price(self):
        return float(self.data.get(CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE))

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

    # ------------------------------------------------------------------
    # Fenster
    # ------------------------------------------------------------------
    @property
    def windows(self):
        """Ein oder mehrere Fensterkontakte (ältere Einträge: einzelner String)."""
        value = self.data.get(CONF_WINDOW)
        if isinstance(value, str):
            return [value] if value else []
        return [w for w in (value or []) if w]

    def open_windows(self):
        return [w for w in self.windows if _is_on(self.hass, w)]

    @property
    def climates(self):
        return [c for c in (self.data.get(CONF_CLIMATES) or []) if c]

    def _serialize_session(self):
        if not self.session:
            return None
        data = dict(self.session)
        data["started"] = self.session["started"].isoformat()
        return data

    async def async_reset_learning(self):
        """Lerndaten verwerfen (z. B. nach Umbau oder falschen Messungen)."""
        self.learned_ach = 8.0
        self.samples = 0
        self.models = {}
        await self._save()
        self._update_recommendation()
        self._notify_listeners()

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

        if stored.get("skip_date"):
            try:
                self._skip_date = datetime.fromisoformat(stored["skip_date"]).date()
            except ValueError:
                self._skip_date = None
        if stored.get("last_session_end"):
            self._last_session_end = dt_util.parse_datetime(stored["last_session_end"])
        self._last_night_low = stored.get("last_night_low")
        self._extras_load(stored)
        self._history_load(stored)

        # Laufende Lüftung aus der Zeit vor dem Neustart übernehmen
        saved = stored.get("session")
        if saved and saved.get("started"):
            started = dt_util.parse_datetime(saved["started"])
            if started is not None:
                self.session = {**saved, "started": started, "restored": True}
                self._target_notified = bool(saved.get("notified"))

        entities = [
            *self.windows,
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
        if self.data.get(CONF_CO2):
            entities.append(self.data[CONF_CO2])
        entities.extend(self.persons)
        entities.extend(self._extras_entities())

        self._remove_listener = async_track_state_change_event(
            self.hass, entities, self._state_changed
        )
        # Reihenfolge laut HA-API: (hass, action, interval)
        self._feedback_remove = async_track_time_interval(
            self.hass, self._feedback_tick, timedelta(seconds=30)
        )
        self._action_remove = self.hass.bus.async_listen(
            "mobile_app_notification_action", self._handle_action
        )
        if self.session:
            await self._resume_session()
        self._update_recommendation()
        if self.data.get(CONF_WEATHER):
            self.hass.async_create_task(self._update_forecast())

    async def _save(self):
        await self.store.async_save({
            "learned_ach": self.learned_ach,
            "samples": self.samples,
            "models": self.models,
            "stats": self.stats,
            "session": self._serialize_session(),
            "skip_date": self._skip_date.isoformat() if self._skip_date else None,
            "last_session_end": self._last_session_end.isoformat() if self._last_session_end else None,
            "last_night_low": self._last_night_low,
            **self._extras_store(),
            **self._history_store(),
        })

    def async_unload(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        if self._feedback_remove:
            self._feedback_remove()
            self._feedback_remove = None
        if self._action_remove:
            self._action_remove()
            self._action_remove = None
        self._clear_issues()

    async def _resume_session(self):
        """Nach Neustart: Fenster noch offen -> weiterlaufen; sicher zu -> abschließen."""
        states = [self.hass.states.get(w) for w in self.windows]
        if any(st is not None and st.state in ON_STATES for st in states):
            return
        known = [st for st in states if st is not None and st.state in OFF_STATES]
        if states and len(known) == len(states):
            ended = max(st.last_changed for st in known)
            await self._finish_session(ended=ended)
        # sonst: Fensterzustand noch unbekannt -> das nächste Ereignis entscheidet

    @callback
    def _handle_action(self, event):
        """Buttons aus der Push-Nachricht."""
        action = event.data.get("action", "")
        if action == f"{ACTION_SNOOZE}{self.entry.entry_id}":
            self._snooze_until = dt_util.now() + timedelta(minutes=SNOOZE_MINUTES)
        elif action == f"{ACTION_SKIP}{self.entry.entry_id}":
            self._skip_date = dt_util.now().date()
            self.hass.async_create_task(self._save())

    @callback
    def _state_changed(self, event):
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")

        if entity_id in self.persons and new_state is not None:
            old_state = event.data.get("old_state")
            if new_state.state == "home" and (old_state is None or old_state.state != "home"):
                self.hass.async_create_task(self._welcome_home(entity_id))
            elif new_state.state != "home" and old_state is not None and old_state.state == "home":
                self.hass.async_create_task(self._left_with_window_open())

        if entity_id == self.data.get(CONF_SHOWER) and new_state is not None:
            self._shower_sensor_changed(event.data.get("old_state"), new_state)

        if entity_id in self.windows and new_state is not None:
            old_state = event.data.get("old_state")
            # Attribut-Änderungen (z. B. Batterie) ändern nichts an der Lüftung
            if old_state is None or old_state.state != new_state.state:
                open_now = self.open_windows()
                if open_now and not self.session:
                    self._start_session()
                elif not open_now and self.session and new_state.state in OFF_STATES:
                    # Lüftung endet erst, wenn ALLE Fenster zu sind
                    self.hass.async_create_task(self._finish_session())
                if self.session and len(open_now) >= 2 and not self.session.get("cross"):
                    self.session["cross"] = True
                    self.hass.async_create_task(self._save())

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

    def _forecast_wind_factor(self, item):
        """0..1 – wie günstig die Windrichtung einer Vorhersage-Stunde fürs Fenster steht.

        Manche Wetter-Integrationen liefern pro Stunde eine Windrichtung (wind_bearing). Steht der
        Wind ungünstig (bläst vom Fenster weg), bringt auch viel Windgeschwindigkeit keinen
        zusätzlichen Luftwechsel - andersherum hilft günstiger Wind besonders. Ohne Richtungsangabe
        in der Vorhersage (nicht jede Integration liefert das) bleibt es wie bisher beim reinen
        Geschwindigkeits-Bonus (Faktor 1)."""
        bearing = _num(item.get("wind_bearing"))
        if bearing is None:
            return 1.0
        source_dir = (
            bearing if self.data.get(CONF_WIND_IS_FROM, True) else (bearing + 180) % 360
        )
        angle = _angle_diff(float(self.data[CONF_WINDOW_DIRECTION]), source_dir)
        return max(0.0, 1 - angle / 180)

    def _bucket(self, wind, angle, temp_diff, cross=False):
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

        key = f"wind:{wb}|angle:{ab}|temp:{tb}"
        # Querlüften getrennt lernen – bisherige Modelle bleiben gültig
        return f"{key}|cross" if cross else key

    def _model_ach(self, wind, angle, temp_diff, cross=False):
        key = self._bucket(wind, angle, temp_diff, cross)
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
            "initial_indoor": indoor,
            "initial_co2": self.co2,
            "dT": self._signed_temp_diff(),
            "wind": wind,
            "angle": angle,
            "temp_diff": temp_diff,
            "target_reached": False,
            "cross": len(self.open_windows()) >= 2,
            "notified": False,
            "cool_warned": False,
            "overtime_warned": False,
            "heating": None,
            "cooling": self.cooling_minutes() > 0 and (diff is None or diff <= DEFAULT_TARGET_DIFF),
            "preheat": self.preheat_minutes() > 0 and (diff is None or diff <= DEFAULT_TARGET_DIFF),
            "trace": [[0, indoor, _float_state(self.hass, self.data[CONF_INDOOR_TEMP])]],
        }
        self._warm_warned = False
        self._session_start_diff = diff
        self._target_notified = False
        self.hass.async_create_task(self._save())

    def _target_reached_now(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        if indoor is None or outdoor is None:
            return False, None
        current_diff = indoor - outdoor
        session = self.session or {}
        if session and self.current_duration_seconds < TARGET_MIN_SECONDS:
            return False, current_diff

        target_abs = float(self.data.get(CONF_TARGET_ABS, DEFAULT_TARGET_ABS))
        start_indoor = session.get("initial_indoor")
        start_diff = session.get("initial_diff")

        # 1) Feuchteunterschied fast ausgeglichen
        if current_diff <= DEFAULT_TARGET_DIFF:
            return True, current_diff
        # 2) Tagesziel unterschritten – aber nur, wenn es beim Öffnen noch darüber lag
        if indoor <= target_abs and (start_indoor is None or start_indoor > target_abs):
            return True, current_diff
        # 3) Großteil des Unterschieds abgebaut (wichtig im Winter, wo außen sehr trocken ist)
        if start_diff and start_diff > 0 and current_diff <= start_diff * (1 - TARGET_PROGRESS):
            return True, current_diff
        # 4) Zum Kühlen gelüftet und Wohlfühltemperatur erreicht
        if session.get("cooling"):
            temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
            if temp is not None and temp <= self.comfort_temp:
                return True, current_diff
        # 4b) Zum Vorheizen gelüftet und Vorheiz-Schwelle erreicht
        if session.get("preheat"):
            temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
            if temp is not None and temp >= self.preheat_temp:
                return True, current_diff
        # 5) Lüftung wegen CO₂ gestartet und Luft wieder gut
        co2 = self.co2
        start_co2 = session.get("initial_co2")
        if (
            start_co2 is not None and start_co2 >= CO2_ELEVATED
            and (start_diff is None or start_diff <= DEFAULT_TARGET_DIFF)
            and co2 is not None and co2 <= CO2_TARGET
        ):
            return True, current_diff
        return False, current_diff

    async def _feedback_tick(self, _now=None):
        try:
            await self._feedback_tick_inner()
        finally:
            # Immer zuletzt, egal an welcher Stelle oben zurückgesprungen wird –
            # sonst zeigt die Karte einen veralteten Stand (z. B. Heizung noch nicht als
            # abgesenkt), bis die nächste Runde in 30 s läuft.
            self._notify_listeners()

    async def _feedback_tick_inner(self, _now=None):
        self._check_sensor_health()
        if self._track_night_low(dt_util.now()):
            await self._save()
        if self._roll_periods():
            await self._save()
        if self._forecast_due():
            await self._update_forecast()
        await self._extras_tick()
        await self._history_tick(dt_util.now())
        self._update_recommendation()
        if not self.session:
            return
        if not self.open_windows():
            return

        await self._check_heating()
        await self._check_warnings()

        reached, current_diff = self._target_reached_now()
        if not reached:
            return
        self.session["target_reached"] = True

        if self._target_notified:
            return
        self._target_notified = True
        self.session["notified"] = True
        await self._save()

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

    # ------------------------------------------------------------------
    # Reparatur-Hinweise bei ausgefallenen Sensoren
    # ------------------------------------------------------------------
    def _required_sensors(self):
        return {
            self.data[CONF_INDOOR_HUMIDITY]: "Absolute Feuchte innen",
            self.data[CONF_OUTDOOR_HUMIDITY]: "Absolute Feuchte außen",
            self.data[CONF_INDOOR_TEMP]: "Temperatur innen",
            self.data[CONF_OUTDOOR_TEMP]: "Temperatur außen",
            **{w: "Fensterkontakt" for w in self.windows},
        }

    def _issue_id(self, entity_id):
        return f"unavailable_{self.entry.entry_id}_{entity_id.replace('.', '_')}"

    def _check_sensor_health(self):
        now = dt_util.now()
        for entity_id, role in self._required_sensors().items():
            state = self.hass.states.get(entity_id)
            broken = state is None or state.state in ("unavailable", "unknown")
            issue_id = self._issue_id(entity_id)
            if not broken:
                if self._unavailable_since.pop(entity_id, None) is not None:
                    ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                continue
            since = self._unavailable_since.setdefault(entity_id, now)
            if (now - since).total_seconds() >= ISSUE_AFTER_MINUTES * 60:
                ir.async_create_issue(
                    self.hass, DOMAIN, issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="sensor_unavailable",
                    translation_placeholders={
                        "room": str(self.data.get(CONF_NAME)),
                        "role": role,
                        "entity": entity_id,
                        "minutes": str(ISSUE_AFTER_MINUTES),
                    },
                )

    def _clear_issues(self):
        for entity_id in self._required_sensors():
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(entity_id))

    # ------------------------------------------------------------------
    # Warnungen während des Lüftens
    # ------------------------------------------------------------------
    @property
    def cooling_down(self):
        """Fenster offen und Raum unter der Auskühl-Grenze."""
        if not self.session or not self.open_windows():
            return False
        limit = float(self.data.get(CONF_COOL_LIMIT, DEFAULT_COOL_LIMIT) or 0)
        temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        return limit > 0 and temp is not None and temp < limit

    async def _check_warnings(self):
        name = self.data[CONF_NAME]
        tag = f"smart_ventilation_{self.entry.entry_id}_warn"

        if self.cooling_down and not self.session.get("cool_warned"):
            self.session["cool_warned"] = True
            temp = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
            await self._send(
                f"Raum kühlt aus: {name}",
                f"Nur noch {temp:.1f} °C bei offenem Fenster – bitte schließen.",
                tag,
            )
            await self._save()

        if self.season == SEASON_WINTER and not self.session.get("overtime_warned"):
            limit = self._winter_max_minutes()
            minutes = self.current_duration_seconds / 60
            if minutes >= limit + WINTER_OVERTIME_MINUTES:
                self.session["overtime_warned"] = True
                await self._send(
                    f"Fenster noch offen: {name}",
                    (
                        f"Seit {minutes:.0f} Minuten gelüftet – bei diesen Temperaturen "
                        f"reichen {limit} Minuten Stoßlüften."
                    ),
                    tag,
                )
                await self._save()

    # ------------------------------------------------------------------
    # Heizung beim Lüften absenken und danach wiederherstellen
    # ------------------------------------------------------------------
    async def _call(self, domain, service, data):
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
            return True
        except Exception:  # noqa: BLE001 – ein Thermostat offline darf nichts blockieren
            return False

    async def _check_heating(self):
        if not self.climates or self.session.get("heating") is not None:
            return
        if self.current_duration_seconds < HEATING_DELAY_SECONDS:
            return

        saved = {}
        external = {}
        for entity_id in self._heating_targets():
            if manager := self._window_managed_by(entity_id):
                external[entity_id] = manager   # regelt selbst beim Fensteröffnen -> nicht eingreifen
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("off", "unavailable", "unknown"):
                continue
            modes = state.attributes.get("hvac_modes") or []
            if "off" in modes:
                if await self._call("climate", "set_hvac_mode",
                                    {"entity_id": entity_id, "hvac_mode": "off"}):
                    saved[entity_id] = {"mode": state.state}
            else:
                target = state.attributes.get("temperature")
                if target is None:
                    continue
                low = state.attributes.get("min_temp", 7)
                if await self._call("climate", "set_temperature",
                                    {"entity_id": entity_id, "temperature": low}):
                    saved[entity_id] = {"temperature": target}

        self.session["heating"] = saved
        self.session["heating_external"] = external
        await self._save()

    # --- Heizungs-Hierarchie: Better Thermostat -> (Climate Group Helper / Gruppe) -> Thermostate ---
    def _climate_children(self, entity_id):
        """Direkt untergeordnete Thermostate: bei Better Thermostat die gesteuerten Geräte, bei Gruppen die Mitglieder."""
        bt = self._integration_config(entity_id, "better_thermostat")
        if bt is not None:
            heaters = bt.get("thermostat") or []
            return [h.get("trv") for h in heaters if isinstance(h, dict) and h.get("trv")]
        state = self.hass.states.get(entity_id)
        members = state.attributes.get("entity_id") if state is not None else None
        if isinstance(members, (list, tuple)):
            return [m for m in members if str(m).startswith("climate.")]
        return []

    def _integration_config(self, entity_id, domain):
        """Einstellungen (data + options) der Integration, falls die Entität zu `domain` gehört."""
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry is None or entry.platform != domain or not entry.config_entry_id:
            return None
        config = self.hass.config_entries.async_get_entry(entry.config_entry_id)
        if config is None:
            return None
        return {**config.data, **config.options}

    def _heating_targets(self):
        """Welche Thermostate schalten? Immer die oberste Ebene, jede nur einmal.

        - Liegt ein gewähltes Thermostat/eine Gruppe unter einem Better Thermostat,
          wird das Better Thermostat geschaltet (sonst würde BT dagegen regeln).
        - Ist ein Thermostat Mitglied einer ebenfalls gewählten Gruppe, wird nur die Gruppe geschaltet.
        """
        parent = {}
        for state in self.hass.states.async_all("climate"):
            for child in self._climate_children(state.entity_id):
                # Better Thermostat hat Vorrang als übergeordnete Ebene
                if child not in parent or self._integration_config(state.entity_id, "better_thermostat") is not None:
                    parent[child] = state.entity_id
        selected = set(self.climates)
        result = []
        for entity_id in self.climates:
            chain, node = [], entity_id
            while node in parent and node not in chain:
                chain.append(node)
                node = parent[node]
            chain.append(node)
            ancestors = chain[1:]
            bt = [a for a in ancestors if self._integration_config(a, "better_thermostat") is not None]
            chosen = [a for a in ancestors if a in selected]
            if bt:
                result.append(bt[-1])
            elif chosen:
                result.append(chosen[-1])
            else:
                result.append(entity_id)
        return list(dict.fromkeys(result))

    def _window_managed_by(self, entity_id, _seen=None):
        """Regelt diese Heizung (oder eine Ebene darunter) beim Fensteröffnen selbst?"""
        seen = _seen or set()
        if entity_id in seen:
            return None
        seen.add(entity_id)
        bt = self._integration_config(entity_id, "better_thermostat")
        if bt is not None and bt.get("window_sensors"):
            return "Better Thermostat"
        cgh = self._integration_config(entity_id, "climate_group_helper")
        if cgh is not None and (cgh.get("room_sensor") or cgh.get("zone_sensor")) and str(
            cgh.get("window_mode") or "disabled"
        ) not in ("disabled", "off"):
            return "Climate Group Helper"
        for child in self._climate_children(entity_id):
            if manager := self._window_managed_by(child, seen):
                return manager
        return None

    async def _restore_heating(self, saved):
        for entity_id, before in (saved or {}).items():
            if "mode" in before:
                await self._call("climate", "set_hvac_mode",
                                 {"entity_id": entity_id, "hvac_mode": before["mode"]})
            elif "temperature" in before:
                await self._call("climate", "set_temperature",
                                 {"entity_id": entity_id, "temperature": before["temperature"]})

    # ------------------------------------------------------------------
    # Bester Lüftungszeitpunkt aus der stündlichen Wettervorhersage
    # ------------------------------------------------------------------
    def _forecast_due(self):
        if not self.data.get(CONF_WEATHER):
            return False
        if self._forecast_checked is None:
            return True
        wait = FORECAST_REFRESH_MINUTES if self.best_info.get("ok") else FORECAST_RETRY_MINUTES
        return (dt_util.now() - self._forecast_checked).total_seconds() >= wait * 60

    async def _fetch_hourly_forecast(self, entity_id):
        response = await self.hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "hourly"},
            blocking=True,
            return_response=True,
        )
        return (response or {}).get(entity_id, {}).get("forecast", [])

    async def _fetch_daily_forecast(self, entity_id):
        response = await self.hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": "daily"},
            blocking=True,
            return_response=True,
        )
        return (response or {}).get(entity_id, {}).get("forecast", [])

    async def _update_forecast(self):
        self._forecast_checked = dt_util.now()
        entity_id = self.data.get(CONF_WEATHER)
        try:
            forecast = await self._fetch_hourly_forecast(entity_id)
        except Exception:  # noqa: BLE001 – z. B. Dienst ohne Stundenvorhersage
            self._set_best(None, "Wetterdaten nicht verfügbar (stündliche Vorhersage?)", {})
            return
        self._evaluate_forecast(forecast)
        self.cool_plan = self.cooling_plan(forecast)
        self.preheat_plan_text = self.preheat_plan(forecast)
        self._rain_soon = self._forecast_rain_soon(forecast)
        try:
            daily = await self._fetch_daily_forecast(entity_id)
        except Exception:  # noqa: BLE001 – z. B. Dienst ohne Tagesvorhersage
            daily = []
        self._forecast_season = self._forecast_season_trend(daily)
        self._notify_listeners()

    def _forecast_season_trend(self, forecast):
        """Aus der Tages-Vorhersage: 'summer'/'winter', wenn Hoch UND Tief an mehreren Tagen
        am Stück eindeutig auf einer Seite der Heizgrenze liegen - ein einzelner Ausreißertag
        reicht nicht. Sonst None (kein verlässlicher Trend, dann entscheidet weiter die lokale
        Messung mit Bestätigungszeit, siehe SEASON_CONFIRM_HOURS)."""
        threshold = float(self.data.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD))
        now = dt_util.now()
        days = []
        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            high = _num(item.get("temperature"))
            low = _num(item.get("templow"))
            if when is None or high is None or low is None:
                continue
            when = dt_util.as_local(when)
            if when < now - timedelta(hours=12) or when > now + timedelta(days=SEASON_FORECAST_DAYS):
                continue
            days.append((high, low))
        if len(days) < 2:
            return None
        if all(low > threshold + SEASON_HYSTERESIS for _, low in days):
            return SEASON_SUMMER
        if all(high < threshold - SEASON_HYSTERESIS for high, _ in days):
            return SEASON_WINTER
        return None

    def _forecast_rain_soon(self, forecast):
        """True, wenn laut Vorhersage in den nächsten Stunden Regen droht - auch wenn es
        gerade noch trocken ist. Verhindert, dass zum Vorheizen geöffnet wird, kurz bevor
        es zu regnen anfängt."""
        now = dt_util.now()
        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            if when is None:
                continue
            when = dt_util.as_local(when)
            hours_ahead = (when - now).total_seconds() / 3600
            if hours_ahead < -0.25 or hours_ahead > PREHEAT_RAIN_LOOKAHEAD_HOURS:
                continue
            rain = _num(item.get("precipitation")) or 0.0
            rain_prob = _num(item.get("precipitation_probability")) or 0.0
            if rain > FORECAST_MAX_RAIN_MM or rain_prob >= FORECAST_MAX_RAIN_PROB:
                return True
        return False

    def _set_best(self, when, reason, info):
        self.best_time = when
        self.best_reason = reason
        self.best_info = info

    def _evaluate_forecast(self, forecast):
        """Bewertet jede Stunde: Feuchtegewinn + Wind, abzüglich Regen/Hitze, Bonus für Wärme im Winter."""
        indoor_ah = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        indoor_t = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        if indoor_ah is None:
            self._set_best(None, "Innenwerte fehlen", {})
            return
        if not forecast:
            self._set_best(None, "Warte auf Wetterdaten", {})
            return

        now = dt_util.now()
        season = self.season
        max_warmer = float(self.data.get(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF))
        best = None
        has_humidity = False

        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            if when is None:
                continue
            when = dt_util.as_local(when)
            if item.get("humidity") is not None or item.get("dew_point") is not None:
                has_humidity = True
            hours_ahead = (when - now).total_seconds() / 3600
            if hours_ahead < -0.5 or hours_ahead > FORECAST_HOURS:
                continue
            if not FORECAST_DAY_START <= when.hour < FORECAST_DAY_END:
                continue

            temp = _num(item.get("temperature"))
            outdoor_ah = _absolute_humidity(
                temp, _num(item.get("humidity")), _num(item.get("dew_point"))
            )
            if outdoor_ah is None:
                continue

            rain = _num(item.get("precipitation")) or 0.0
            rain_prob = _num(item.get("precipitation_probability")) or 0.0
            if rain > FORECAST_MAX_RAIN_MM or rain_prob >= FORECAST_MAX_RAIN_PROB:
                continue
            if (
                season == SEASON_SUMMER
                and indoor_t is not None
                and temp - indoor_t > max_warmer
            ):
                continue

            gain = indoor_ah - outdoor_ah
            if gain < FORECAST_MIN_GAIN:
                continue

            wind = _num(item.get("wind_speed")) or 0.0
            score = gain + min(wind, 30) / 60 * self._forecast_wind_factor(item)
            if season == SEASON_WINTER:
                score += 0.15 * temp  # wärmere Stunde = weniger Wärmeverlust
            elif indoor_t is not None:
                score -= 0.3 * max(0.0, temp - indoor_t)

            if best is None or score > best[0]:
                best = (score, when, temp, outdoor_ah, gain, rain_prob)

        if not has_humidity:
            self._set_best(None, "Vorhersage enthält keine Luftfeuchte", {"ok": True})
            return
        if best is None:
            self._set_best(None, "Heute kein geeigneter Zeitpunkt", {"ok": True})
            return

        _, when, temp, outdoor_ah, gain, rain_prob = best
        day = "Heute" if when.date() == now.date() else "Morgen"
        self._set_best(
            when,
            f"{day} {when.strftime('%H:%M')} Uhr",
            {
                "ok": True,
                "aussen_temperatur": round(temp, 1),
                "aussen_feuchte_abs": round(outdoor_ah, 1),
                "feuchte_gewinn": round(gain, 1),
                "regenwahrscheinlichkeit": round(rain_prob),
            },
        )

    @property
    def notify_targets(self):
        """Gewählte notify-Dienste; ältere Einträge nutzen noch das Textfeld."""
        targets = self.data.get(CONF_NOTIFY_SERVICES)
        if targets is None:
            legacy = (self.data.get(CONF_NOTIFY_SERVICE) or "").strip()
            targets = [legacy] if legacy else []
        return [t for t in targets if isinstance(t, str) and t.startswith("notify.")]

    async def _send(self, title, message, tag, actions=None, targets=None):
        return await notify_util.send(
            self.hass,
            self.notify_targets if targets is None else targets,
            title, message, tag, actions,
        )

    def _session_energy_kwh(self, session, elapsed):
        """Wärmeverlust durch Luftaustausch: 0,34 Wh/(m³K) · V · ΔT · (1 − e^(−n·t))."""
        d_t = session.get("dT")
        if d_t is None or d_t <= 0:
            return 0.0
        n, _ = self._model_ach(
            session.get("wind"), session.get("angle"), session.get("temp_diff"),
            session.get("cross", False),
        )
        volume = float(self.data.get(CONF_VOLUME, 40))
        exchanged = 1 - math.exp(-n * elapsed / 3600)
        return AIR_HEAT_CAPACITY_WH * volume * d_t * exchanged / 1000

    def _session_preheat_savings_kwh(self, session, elapsed):
        """Eingesparte Heizenergie durchs Vorheizen: die wärmere Außenluft erwärmt den Raum,
        ohne dass dafür geheizt werden muss – spiegelbildlich zu _session_energy_kwh (dort:
        Wärmeverlust durch Lüften). Nur für als "preheat" markierte Sitzungen, und nur, wenn es
        zum Sitzungsstart draußen tatsächlich wärmer war als drinnen (dT < 0)."""
        if not session.get("preheat"):
            return 0.0
        d_t = session.get("dT")
        if d_t is None or d_t >= 0:
            return 0.0
        n, _ = self._model_ach(
            session.get("wind"), session.get("angle"), session.get("temp_diff"),
            session.get("cross", False),
        )
        volume = float(self.data.get(CONF_VOLUME, 40))
        exchanged = 1 - math.exp(-n * elapsed / 3600)
        return AIR_HEAT_CAPACITY_WH * volume * abs(d_t) * exchanged / 1000

    def _record_stats(self, elapsed, success, kwh=0.0, saved_kwh=0.0):
        self._roll_periods()
        for period in ("day", "week", "month", "total"):
            p = self.stats[period]
            p["count"] += 1
            p["seconds"] += elapsed
            p["kwh"] = p.get("kwh", 0.0) + kwh
            p["kwh_gespart"] = p.get("kwh_gespart", 0.0) + saved_kwh
            if success:
                p["ok"] += 1
            else:
                p["short"] += 1
        self.stats["max_seconds"] = max(self.stats.get("max_seconds", 0.0), elapsed)

    async def _finish_session(self, ended=None):
        if not self.session:
            return

        session = self.session
        self.session = None
        self._session_start_diff = None

        await self._restore_heating(session.get("heating"))
        self._trace_finish(session)

        elapsed = ((ended or dt_util.now()) - session["started"]).total_seconds()
        restored = session.get("restored", False)

        # Kurzes Auf/Zu (< 30 s) zählt nicht; nach Neustart nur plausible Dauer zählen
        if elapsed >= 30 and not (restored and elapsed > DEFAULT_MAX_SESSION):
            if restored:
                # Über einen Neustart hinweg können zwischen dem tatsächlichen Fensterschluss
                # und diesem Abschluss hier Stunden liegen - die AKTUELLEN Sensorwerte sagen
                # dann nichts mehr darüber aus, ob damals das Ziel erreicht wurde. Nur zählen,
                # was schon vor dem Neustart als erreicht gespeichert war.
                reached = False
            else:
                self.session = session  # Startwerte für die Zielprüfung bereitstellen
                reached, _ = self._target_reached_now()
                self.session = None
            success = (
                elapsed >= DEFAULT_MIN_SESSION
                and (session["target_reached"] or reached)
            )
            self._record_stats(
                elapsed,
                success,
                self._session_energy_kwh(session, elapsed),
                self._session_preheat_savings_kwh(session, elapsed),
            )
            self._last_session_end = ended or dt_util.now()
        await self._save()
        self._notify_listeners()

        # Über einen Neustart hinweg ist der Feuchteverlauf unbekannt -> nicht lernen
        if restored or elapsed < DEFAULT_MIN_SESSION or elapsed > DEFAULT_MAX_SESSION:
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
            session["wind"], session["angle"], session["temp_diff"],
            session.get("cross", False),
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
        """'summer' oder 'winter' – manuell gesetzt oder automatisch per Kalendermonat/Außentemperatur.

        Dezember–Februar und Juni–August gelten fest als Winter bzw. Sommer, ein einzelner
        milder Wintertag oder kühler Sommertag soll den Modus nicht umschalten. Nur in den
        Übergangsmonaten (März–Mai, September–November) entscheidet es sich sonst:

        1. Zeigt die mehrtägige Wettervorhersage (falls eine Wetter-Entität gewählt ist) schon
           einen eindeutigen Trend – Hoch UND Tief mehrere Tage am Stück klar auf einer Seite
           der Heizgrenze –, wird das sofort übernommen. Das ist ein verlässlicheres Signal als
           ein paar Stunden lokale Messwerte.
        2. Sonst entscheidet die aktuelle Außentemperatur – und zwar erst, wenn sie deutlich
           über/unter der Schwelle liegt (Hysterese) UND das schon einige Stunden ununterbrochen
           so ist (SEASON_CONFIRM_HOURS). Sonst würde an Tagen mit großer Tag/Nacht-Schwankung
           (kalte Nacht, warmer Nachmittag) der Modus mehrmals täglich hin- und herspringen,
           obwohl sich an der eigentlichen Jahreszeit nichts geändert hat.
        """
        mode = self.data.get(CONF_SEASON_MODE, DEFAULT_SEASON_MODE)
        if mode in (SEASON_SUMMER, SEASON_WINTER):
            return mode

        month = dt_util.now().month
        if month in SEASON_FIXED_WINTER_MONTHS:
            self._auto_season = SEASON_WINTER
            self._season_pending = None
            return SEASON_WINTER
        if month in SEASON_FIXED_SUMMER_MONTHS:
            self._auto_season = SEASON_SUMMER
            self._season_pending = None
            return SEASON_SUMMER

        if (
            self.data.get(CONF_WEATHER)
            and self._forecast_season in (SEASON_SUMMER, SEASON_WINTER)
            and self._forecast_season != self._auto_season
        ):
            self._auto_season = self._forecast_season
            self._season_pending = None
            self._season_pending_since = None
            return self._auto_season

        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        threshold = float(self.data.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD))
        if outdoor is None:
            return self._auto_season or SEASON_WINTER

        # Hysterese: im Bereich Schwelle ± 1 °C ändert sich der Kandidat nicht.
        if outdoor < threshold - SEASON_HYSTERESIS:
            candidate = SEASON_WINTER
        elif outdoor > threshold + SEASON_HYSTERESIS:
            candidate = SEASON_SUMMER
        else:
            candidate = None

        if self._auto_season is None:
            # Erststart: sofort einordnen, nicht erst stundenlang abwarten.
            self._auto_season = candidate or (SEASON_WINTER if outdoor < threshold else SEASON_SUMMER)
            self._season_pending = None
            return self._auto_season

        now = dt_util.now()
        if candidate is None or candidate == self._auto_season:
            # Zurück in die Mitte oder wieder wie bisher -> ein evtl. laufender Wechsel zählt nicht mehr.
            self._season_pending = None
            self._season_pending_since = None
        elif candidate != self._season_pending:
            self._season_pending = candidate
            self._season_pending_since = now
        elif now - self._season_pending_since >= timedelta(hours=SEASON_CONFIRM_HOURS):
            self._auto_season = candidate
            self._season_pending = None
            self._season_pending_since = None
        return self._auto_season

    def _track_night_low(self, now):
        """Nacht-Tiefsttemperatur (22–9 Uhr) merken - Grundlage fürs Vorheizen: hat es in der
        letzten Nacht schon nach Heizsaison ausgesehen? Gibt True zurück, wenn eine Nacht gerade
        abgeschlossen wurde (dann muss gespeichert werden)."""
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        in_night = now.hour >= NIGHT_LOW_START_HOUR or now.hour < NIGHT_LOW_END_HOUR
        if in_night:
            if outdoor is not None:
                self._night_low = outdoor if self._night_low is None else min(self._night_low, outdoor)
            return False
        if self._night_low is not None:
            self._last_night_low = self._night_low
            self._night_low = None
            return True
        return False

    def _temperature_block(self):
        """Sperren, wenn es draußen deutlich wärmer ist als drinnen – unabhängig von der
        Jahreszeit. Das gilt nicht nur im Sommer (Kühleffekt verpufft), sondern auch an
        milden Tagen im Winter: Lüften heizt den Raum dann unnötig auf, statt ihn zu kühlen
        oder zu trocknen."""
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

    async def _welcome_home(self, person):
        """Beim Heimkommen einmal erinnern, falls Lüften fällig ist."""
        self._update_recommendation()
        now = dt_util.now()
        if not self.reminder_allowed(now) or self._combined_by_overview():
            return
        if self.in_quiet_hours(now) or self._skip_date == now.date():
            return
        targets = notify_util.filter_targets(
            self.hass, self.notify_targets, self.persons, only_person=person
        )
        if not targets:
            return
        await self._send(
            f"Willkommen zu Hause – {self.data[CONF_NAME]}",
            f"{self.data[CONF_NAME]} sollte gelüftet werden: {self.recommendation}",
            f"smart_ventilation_{self.entry.entry_id}",
            targets=targets,
        )

    def pause_reason(self, now=None):
        """Warum gerade nicht zum Lüften aufgefordert wird (gleiche Regeln wie bei Benachrichtigungen)."""
        now = now or dt_util.now()
        if self.recommended_minutes <= 0 or self.session or self.open_windows():
            return None
        if self.on_vacation:
            return "Urlaub"
        if not self._extreme_now():
            until = self._post_vent_pause_until()
            if until is not None and now < until:
                from_forecast = until != dt_util.as_local(self._last_session_end) + timedelta(minutes=POST_VENT_PAUSE_MINUTES)
                suffix = " (nächster günstiger Zeitpunkt)" if from_forecast else ""
                return f"Pause nach dem Lüften bis {until.strftime('%H:%M')} Uhr{suffix}"
        skip, snooze = self._skip_date, self._snooze_until
        for other in self.hass.data.get(DOMAIN, {}).values():
            if getattr(other, "is_overview", False) and other.combine:
                skip = skip or getattr(other, "_skip_date", None)
                snooze = snooze or getattr(other, "_snooze_until", None)
        if skip == now.date():
            return "Heute nicht mehr erinnern"
        if snooze is not None and now < snooze:
            return f"Erinnerung um {dt_util.as_local(snooze).strftime('%H:%M')} Uhr"
        if self.in_quiet_hours(now):
            end = str(self.data.get(CONF_QUIET_END) or DEFAULT_QUIET_END)[:5]
            return f"Ruhezeit bis {end} Uhr"
        if not self.anyone_home:
            return "Niemand zu Hause"
        return None

    def in_quiet_hours(self, now=None):
        return notify_util.in_quiet_hours(
            now or dt_util.now(),
            self.data.get(CONF_QUIET_START), self.data.get(CONF_QUIET_END),
            DEFAULT_QUIET_START, DEFAULT_QUIET_END,
        )

    @property
    def persons(self):
        return [p for p in (self.data.get(CONF_PERSONS) or []) if p]

    @property
    def anyone_home(self):
        return notify_util.anyone_home(self.hass, self.persons)

    def _combined_by_overview(self):
        """Übersicht mit Sammel-Benachrichtigung vorhanden -> Raum schickt keine eigenen Erinnerungen."""
        for other in self.hass.data.get(DOMAIN, {}).values():
            if getattr(other, "is_overview", False) and other.combine:
                return True
        return False

    def _extreme_now(self):
        """Lage so ernst, dass auch eine laufende Pause nicht mehr gilt (Schimmel oder CO₂ hoch)."""
        return self.mold_risk == "hoch" or (self.co2 is not None and self.co2 >= CO2_HIGH)

    def _post_vent_pause_until(self):
        """Bis wann nach dem Lüften nicht erneut erinnert wird.

        Normalerweise POST_VENT_PAUSE_MINUTES nach Sessionende. Ist eine Wetter-Entität
        eingerichtet und die Vorhersage nennt einen späteren guten Lüftungszeitpunkt
        (max. POST_VENT_FORECAST_MAX_HOURS Stunden voraus), gilt stattdessen dieser –
        dann wird nicht schon nach 60 Minuten wieder erinnert, obwohl es draußen
        gerade ungünstig ist (z. B. Regen, Hitze). Bei Schimmel- oder CO₂-Alarm greift
        die Pause ohnehin nicht, siehe _extreme_now().
        """
        if self._last_session_end is None:
            return None
        end = dt_util.as_local(self._last_session_end)
        fallback = end + timedelta(minutes=POST_VENT_PAUSE_MINUTES)
        if not self.data.get(CONF_WEATHER) or self.best_time is None:
            return fallback
        best = dt_util.as_local(self.best_time)
        if end < best <= end + timedelta(hours=POST_VENT_FORECAST_MAX_HOURS):
            return best
        return fallback

    def reminder_allowed(self, now=None):
        """Darf dieser Raum gerade an Lüften erinnern? (auch von der Übersicht genutzt)"""
        now = now or dt_util.now()
        if self.recommended_minutes <= 0 or self.session or self.open_windows():
            return False
        if self.on_vacation:
            return False
        if self.block_reason and "Sonne" not in self.block_reason and "CO₂" not in self.block_reason:
            return False
        if not self._extreme_now():
            pause_until = self._post_vent_pause_until()
            if pause_until is not None and now < pause_until:
                return False
        return True

    def _notification_key(self):
        if self.recommended_minutes <= 0:
            return None
        return f"{self.recommended_mode}|{self.block_reason}"

    async def _send_notification_if_needed(self):
        if not self.notify_targets or not self.reminder_allowed():
            return
        if self._combined_by_overview():
            return
        # Niemand zu Hause -> keine Erinnerung (Hinweis kommt beim Heimkommen)
        if not self.anyone_home:
            return

        key = self._notification_key()
        if key is None:
            return

        now = dt_util.now()
        if self.in_quiet_hours(now) or self._skip_date == now.date():
            return

        snooze_over = False
        if self._snooze_until is not None:
            if now < self._snooze_until:
                return
            self._snooze_until = None
            snooze_over = True  # "In 30 Min. erinnern" – Cooldown einmal überspringen

        cooldown_s = int(
            self.data.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
        ) * 60

        # Cooldown gilt global, nicht nur pro identischer Meldung
        if (
            not snooze_over
            and self.last_notification_at is not None
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
            targets=notify_util.filter_targets(
                self.hass, self.notify_targets, self.persons, only_home=True
            ),
            actions=[
                {"action": f"{ACTION_SNOOZE}{self.entry.entry_id}",
                 "title": f"In {SNOOZE_MINUTES} Min. erinnern"},
                {"action": f"{ACTION_SKIP}{self.entry.entry_id}",
                 "title": "Heute nicht mehr"},
            ],
        )
        if sent:
            self.last_notification_key = key
            self.last_notification_at = now

    def _humidity_need(self, indoor, diff):
        """Wegen Feuchte lüften nur, wenn es sich lohnt UND die Raumluft zu feucht ist.

        - draußen deutlich trockener (ab START_DIFF g/m³)
        - und innen über dem Tagesziel, relative Feuchte hoch oder Schimmelrisiko an der Wand

        Mit Hysterese: Ist die Empfehlung schon aktiv, bleibt sie es, bis entweder der
        Feuchteunterschied ODER alle Einzelgründe (Zielwert, rel. Feuchte, Schimmel) klar
        unter ihrer jeweiligen Schwelle liegen (Puffer einstellbar, siehe CONF_HUMID_HYSTERESIS)
        – genau die Umkehrung der Bedingung oben, nur mit etwas Abstand zur Schwelle. Ohne
        diesen Puffer kippt die Empfehlung bei jeder kleinen Sensorschwankung genau an der
        Schwelle hin und her – sichtbar als ständiger Wechsel zwischen „Kippfenster …“ und
        „Keine Lüftung erforderlich“ im Verlauf.
        """
        target_abs = float(self.data.get(CONF_TARGET_ABS, DEFAULT_TARGET_ABS))
        rh = self.indoor_rh
        mold = self.mold_risk

        enter = diff > START_DIFF and (
            indoor > target_abs
            or (rh is not None and rh >= HUMID_RH)
            or mold in ("erhöht", "hoch")
        )
        if not self._humidity_active:
            self._humidity_active = enter
            return enter

        # aktiv -> aus, sobald der Feuchteunterschied allein klar unter der Schwelle liegt,
        # oder (wenn er das noch nicht tut) alle anderen Gründe klar unter ihrer Schwelle
        # liegen. Nur eines von beidem reicht - so bleibt es beim gleichen Entweder-oder wie
        # bei der Einstiegsbedingung, nur mit Puffer statt einer scharfen Kante.
        hysteresis = float(self.data.get(CONF_HUMID_HYSTERESIS, DEFAULT_HUMID_HYSTERESIS))
        # (1e-6 Toleranz gegen Fließkomma-Rundung, z. B. 10,1 - 9,2 = 0,9000000000000004.)
        diff_clearly_below = diff <= START_DIFF - hysteresis + 1e-6
        reasons_clearly_below = (
            indoor <= target_abs - hysteresis + 1e-6
            and (rh is None or rh < HUMID_RH - hysteresis * HUMID_RH_HYSTERESIS_RATIO)
            and mold not in ("erhöht", "hoch")
        )
        self._humidity_active = not (diff_clearly_below or reasons_clearly_below)
        return self._humidity_active

    def _update_recommendation(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])

        self.block_reason = ""

        if indoor is None or outdoor is None:
            self.recommendation = "Sensordaten fehlen"
            self.recommended_minutes = 0
            return

        diff = indoor - outdoor
        co2 = self.co2
        need_humidity = self._humidity_need(indoor, diff)
        need_co2 = co2 is not None and co2 >= CO2_ELEVATED
        cool_minutes = self.cooling_minutes()
        need_cool = cool_minutes > 0
        preheat_minutes = self.preheat_minutes()
        need_preheat = preheat_minutes > 0
        reasons = [
            r for r, on in (
                ("Feuchte", need_humidity), ("CO₂", need_co2),
                ("Kühlen", need_cool), ("Vorheizen", need_preheat),
            ) if on
        ]
        self.recommend_reason = " + ".join(reasons)

        if not need_humidity and not need_co2 and not need_cool and not need_preheat:
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
        # Sehr schlechte Luft: trotz Hitze kurz lüften
        co2_override = temp_block and co2 is not None and co2 >= CO2_HIGH
        # Vorheizen setzt gerade voraus, dass es draußen wärmer ist - das ist hier der Grund
        # fürs Lüften, keine Sperre.
        preheat_override = temp_block and need_preheat
        if temp_block and not co2_override and not preheat_override:
            self.recommendation = "Nicht lüften – draußen zu warm"
            self.recommended_minutes = 0
            self.recommended_mode = "Geschlossen"
            self.block_reason = temp_reason
            return

        sun_active, direct_sun, sun_reason = self._sun_effect()

        wind, angle, temp_diff = self._context()
        cross = len(self.windows) >= 2
        effective_ach, bucket = self._model_ach(wind, angle, temp_diff, cross)

        if wind is not None:
            effective_ach *= 1 + min(wind / 60, 0.5)
            if angle is not None:
                if angle <= 30:
                    effective_ach *= 1.25
                elif angle <= 60:
                    effective_ach *= 1.10
                else:
                    effective_ach *= 0.9

        minutes = 0.0
        if need_humidity:
            ratio = DEFAULT_TARGET_DIFF / max(diff, DEFAULT_TARGET_DIFF + 0.01)
            minutes = -60 / effective_ach * math.log(ratio)
        if need_co2:
            co2_ratio = (CO2_TARGET - CO2_OUTDOOR) / max(co2 - CO2_OUTDOOR, 1)
            minutes = max(minutes, -60 / effective_ach * math.log(co2_ratio))
        if need_cool:
            minutes = max(minutes, cool_minutes)
        if need_preheat:
            minutes = max(minutes, preheat_minutes)
        minutes = max(2, min(60, minutes))
        if co2_override:
            minutes = min(minutes, 5)
            self.block_reason = f"{temp_reason} – aber CO₂ {co2:.0f} ppm"

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

        if cross and mode != "Kippfenster":
            mode = f"{mode} (Querlüften)"

        self.recommended_minutes = round(minutes)
        self.recommended_mode = mode
        if self.recommend_reason == "Kühlen":
            self.recommended_mode = "Kühlen – Fenster auf"
            self.recommendation = (
                f"Kühlen – Fenster auf bis ca. {self.comfort_temp:.0f} °C "
                f"(ca. {self.recommended_minutes} Min.)"
            )
        elif self.recommend_reason == "Vorheizen":
            self.recommended_mode = "Vorheizen – Fenster auf"
            self.recommendation = (
                f"Vorheizen – warme Luft reinlassen bis ca. {self.preheat_temp:.0f} °C "
                f"(ca. {self.recommended_minutes} Min.)"
            )
        else:
            suffix = " (CO₂)" if self.recommend_reason == "CO₂" else ""
            self.recommendation = f"{mode} – ca. {self.recommended_minutes} Min.{suffix}"
        self.hass.async_create_task(self._send_notification_if_needed())

    @property
    def progress(self):
        """Lüftungsfortschritt in % (Abbau des Feuchteunterschieds seit dem Öffnen)."""
        if not self.session:
            return 0
        initial = self.session.get("initial_diff")
        current = self.humidity_difference
        if initial is None or current is None or initial <= 0:
            return 0
        return round(max(0, min(100, (1 - current / initial) * 100)))

    def _friendly_name(self, entity_id):
        state = self.hass.states.get(entity_id)
        return (state.name if state is not None else None) or entity_id

    def own_entity(self, platform, key):
        """Entity-ID einer eigenen Entität (für Klick-Ziele in der Karte)."""
        return er.async_get(self.hass).async_get_entity_id(
            platform, DOMAIN, f"{self.entry.entry_id}_{key}"
        )

    def card_data(self):
        """Alles, was die Dashboard-Karte braucht, in einem Attribut."""
        r = lambda v, n=1: round(v, n) if v is not None else None  # noqa: E731
        today = self.period_stats("day")
        return {
            "name": self.data.get(CONF_NAME),
            "status": self.recommendation,
            "modus": self.recommended_mode,
            "minuten": self.recommended_minutes,
            "grund": self.recommend_reason,
            "blockiert": self.block_reason,
            "laeuft": self.session is not None,
            "dauer_s": self.current_duration_seconds,
            "fortschritt": self.progress,
            "fenster_offen": len(self.open_windows()),
            "querlueften": bool((self.session or {}).get("cross")),
            "innen_t": r(_float_state(self.hass, self.data[CONF_INDOOR_TEMP])),
            "innen_ah": r(_float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])),
            "innen_rh": r(self.indoor_rh, 0),
            "aussen_t": r(_float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])),
            "aussen_ah": r(_float_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])),
            "wand_t": r(self.wall_temperature),
            "wand_rh": r(self.wall_rh, 0),
            "schimmel": self.mold_risk,
            "co2": r(self.co2, 0),
            "luft": self.air_quality,
            "saison": self.season,
            "bester_zeitpunkt": self.best_reason if self.data.get(CONF_WEATHER) else None,
            "heute_anzahl": today["count"],
            "heute_ok": today["ok"],
            "heute_min": today["minutes"],
            "heute_kwh": today["kwh"],
            "heute_eur": today["cost"],
            "heute_kwh_gespart": today["kwh_gespart"],
            "heute_eur_gespart": today["kosten_gespart"],
            "gelueftet": self.ventilated_today,
            "kuehlt_aus": self.cooling_down,
            "ruhezeit": self.in_quiet_hours(),
            "pausiert": self.pause_reason(),
            "verlauf": self.trace_for_card(),
            "kuehlen_plan": self.cool_plan,
            "vorheizen_plan": self.preheat_plan_text,
            "nach_dusche": self.after_shower,
            "urlaub": self.on_vacation,
            "entfeuchter": self.dehumidifier_active,
            "schimmel_tage": self.mold_streak()[0],
            "fenster_anzahl": len(self.windows),
            "entitaeten": {
                "innen": self.data[CONF_INDOOR_TEMP],
                "aussen": self.data[CONF_OUTDOOR_TEMP],
                "wand": self.own_entity("sensor", "wall_humidity"),
                "co2": self.data.get(CONF_CO2) or None,
                "heute": self.own_entity("sensor", "stats_day"),
                "bester": self.own_entity("sensor", "best_time"),
                "kosten": self.own_entity("sensor", "cost_month"),
            },
            "schimmel_h_heute": self.mold_hours_today,
            "heizung_ab": [self._friendly_name(e) for e in (self.session or {}).get("heating") or {}],
            "heizung_extern": [self._friendly_name(e) for e in (self.session or {}).get("heating_external") or {}],
        }

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

    def _signed_temp_diff(self):
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if indoor is None or outdoor is None:
            return None
        return indoor - outdoor

    @property
    def co2(self):
        entity_id = self.data.get(CONF_CO2)
        return _float_state(self.hass, entity_id) if entity_id else None

    @property
    def air_quality(self):
        co2 = self.co2
        if co2 is None:
            return None
        if co2 >= CO2_HIGH:
            return "schlecht"
        if co2 >= CO2_ELEVATED:
            return "mäßig"
        return "gut"

    @property
    def u_value(self):
        return U_VALUES.get(self.data.get(CONF_BUILDING, DEFAULT_BUILDING), 1.0)

    @property
    def wall_temperature(self):
        """Oberflächentemperatur an der kältesten Stelle: θi − Rsi·U·(θi − θe)."""
        indoor = _float_state(self.hass, self.data[CONF_INDOOR_TEMP])
        outdoor = _float_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if indoor is None or outdoor is None:
            return None
        if outdoor >= indoor:
            return indoor
        return indoor - RSI_CORNER * self.u_value * (indoor - outdoor)

    @property
    def wall_rh(self):
        """Relative Feuchte direkt an der kalten Wand – entscheidend für Schimmel."""
        ah = _float_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        return _relative_humidity_from_absolute(ah, self.wall_temperature)

    @property
    def mold_risk(self):
        wall = self.wall_rh
        if wall is not None:
            if wall >= MOLD_RH_HIGH:
                return "hoch"
            if wall >= MOLD_RH_ELEVATED:
                return "erhöht"
            return "niedrig"
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
