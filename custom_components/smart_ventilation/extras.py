"""Zusatzfunktionen eines Raums: Bad-Modus, Verlassen/Urlaub, Kühlen, Entfeuchter, Wochenbericht, Verlauf.

Als Mixin der Raum-Logik (SmartVentilationCoordinator) – nutzt deren Sensorwerte und Sende-Funktion.
"""
from __future__ import annotations

import math
from collections import deque
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .const import (
    CAT_MOLD, CAT_REPORT, CAT_SHOWER, CAT_WARNING,
    CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF,
    CONF_COMFORT_TEMP, CONF_DEHUMIDIFIER, CONF_SHUTTER, CONF_INDOOR_HUMIDITY, CONF_INDOOR_TEMP, CONF_TARGET_ABS,
    CONF_NAME, CONF_OUTDOOR_HUMIDITY, CONF_OUTDOOR_TEMP, CONF_SHOWER, CONF_SHOWER_DETECT,
    CONF_VACATION, CONF_VACATION_KEYWORD, CONF_WEEKLY_REPORT, COOL_MAX_EXTRA_HUMIDITY,
    COOL_MIN_DIFF, DEFAULT_COMFORT_TEMP, DEFAULT_TARGET_DIFF, DEHUM_MIN_RUNTIME_MINUTES,
    DEHUM_AH_HYSTERESIS, DEHUM_OFF_RH, DEHUM_ON_RH, DEHUM_RH_HYSTERESIS, DEHUM_RESTART_COOLDOWN_MINUTES, SHUTTER_MIN_RUNTIME_MINUTES, DOMAIN, OFF_STATES, ON_STATES, REPORT_HOUR, REPORT_WEEKDAY,
    SEASON_SUMMER, SHOWER_FOLLOWUP_MINUTES, SHOWER_JUMP, SHOWER_WINDOW_MINUTES,
    TRACE_CARD_POINTS, TRACE_MAX_POINTS,
    CONF_PREHEAT_TEMP, DEFAULT_PREHEAT_TEMP, PREHEAT_MIN_WARMER, PREHEAT_MAX_EXTRA_HUMIDITY, CONF_RAIN,
    CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD,
    CONF_SEASON_MODE, DEFAULT_SEASON_MODE,
    FORECAST_MAX_RAIN_MM, FORECAST_MAX_RAIN_PROB, MIN_FORECAST_WIND_FACTOR,
    CONF_SOLAR_RADIATION, SOLAR_RADIATION_MIN, SOLAR_RADIATION_RELEASE,
)
from . import notify_util
from .sensor_utils import _is_raining


def _num_state(hass, entity_id):
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def de_num(value, digits):
    """1.25 -> '1,25' (deutsches Komma)."""
    return f"{value:.{digits}f}".replace(".", ",")


def _week_key(now):
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


class RoomExtrasMixin:
    """Erwartet die Attribute/Methoden des SmartVentilationCoordinator."""

    def _init_extras(self):
        self._shower = None                 # {"at", "start_ah", "vent_after"}
        self._ah_history = deque()          # (Zeit, absolute Feuchte) für Sprungerkennung
        self._last_shower_detect = None
        self._vacation_warned = None        # Datum der letzten Urlaubs-Schimmelwarnung
        self._dehum_on_since = None         # nur gesetzt, wenn WIR eingeschaltet haben
        self._dehum_off_until = None        # Neustart-/Pingpong-Schutz nach dem Ausschalten
        self._shutter_closed_since = None   # nur gesetzt, wenn WIR das Rollo geschlossen haben
        self._shutter_notified = False      # einmalig pro Sonnen-Expositionsfenster benachrichtigt
        self._last_report = None            # Kalenderwoche des letzten Wochenberichts
        self._warm_warned = False
        self.last_trace = None

    # ------------------------------------------------------------------
    # Speichern / Laden
    # ------------------------------------------------------------------
    def _extras_store(self):
        return {
            "last_report": self._last_report,
            "vacation_warned": self._vacation_warned,
            "dehum_on_since": self._dehum_on_since.isoformat() if self._dehum_on_since else None,
            "dehum_off_until": self._dehum_off_until.isoformat() if self._dehum_off_until else None,
            "shutter_closed_since": self._shutter_closed_since.isoformat() if self._shutter_closed_since else None,
            "shutter_notified": self._shutter_notified,
            "last_trace": self.last_trace,
        }

    def _extras_load(self, stored):
        self._last_report = stored.get("last_report")
        self._vacation_warned = stored.get("vacation_warned")
        if stored.get("dehum_on_since"):
            self._dehum_on_since = self._stored_datetime(stored["dehum_on_since"])
        if stored.get("dehum_off_until"):
            self._dehum_off_until = self._stored_datetime(stored["dehum_off_until"])
        if stored.get("shutter_closed_since"):
            self._shutter_closed_since = self._stored_datetime(stored["shutter_closed_since"])
        self._shutter_notified = bool(stored.get("shutter_notified", False))
        trace = stored.get("last_trace")
        if isinstance(trace, dict):
            points = trace.get("punkte")
            if isinstance(points, list):
                valid_points = [
                    point for point in points
                    if isinstance(point, list) and len(point) == 3
                ]
                self.last_trace = {
                    "ende": trace.get("ende"),
                    "punkte": valid_points[-TRACE_MAX_POINTS:],
                } if valid_points else None
            else:
                self.last_trace = None
        else:
            self.last_trace = None

    def _extras_entities(self):
        return [e for e in (self.data.get(CONF_SHOWER), self.data.get(CONF_VACATION)) if e]

    # ------------------------------------------------------------------
    # Verlauf während einer Lüftung (für die Karte)
    # ------------------------------------------------------------------
    def _trace_point(self):
        return [
            self.current_duration_seconds if self.session else 0,
            _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY]),
            _num_state(self.hass, self.data[CONF_INDOOR_TEMP]),
        ]

    def _trace_add(self):
        trace = self.session.setdefault("trace", [])
        if len(trace) < TRACE_MAX_POINTS:
            trace.append(self._trace_point())

    def _trace_finish(self, session):
        points = session.get("trace") or []
        if len(points) >= 2:
            self.last_trace = {"ende": dt_util.now().isoformat(), "punkte": points}

    def trace_for_card(self):
        """Laufende oder letzte Lüftung, auf höchstens 60 Punkte ausgedünnt."""
        running = bool(self.session and self.session.get("trace"))
        points = self.session["trace"] if running else (self.last_trace or {}).get("punkte") or []
        if len(points) > TRACE_CARD_POINTS:
            step = len(points) / TRACE_CARD_POINTS
            points = [points[int(i * step)] for i in range(TRACE_CARD_POINTS)] + [points[-1]]
        return {"laeuft": running, "ende": None if running else (self.last_trace or {}).get("ende"),
                "punkte": points} if points else None

    # ------------------------------------------------------------------
    # Bad-Modus
    # ------------------------------------------------------------------
    @property
    def after_shower(self):
        return self._shower is not None

    def _shower_sensor_changed(self, old_state, new_state):
        """Dusche aus -> Lüften anstoßen."""
        if old_state is not None and old_state.state in ON_STATES and new_state.state in OFF_STATES:
            self.hass.async_create_task(self._shower_event())

    def _detect_humidity_jump(self, now):
        if not self.data.get(CONF_SHOWER_DETECT):
            return False
        ah = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        if ah is None:
            return False
        self._ah_history.append((now, ah))
        while self._ah_history and (now - self._ah_history[0][0]) > timedelta(minutes=SHOWER_WINDOW_MINUTES):
            self._ah_history.popleft()
        low = min(v for _, v in self._ah_history)
        recently = self._last_shower_detect and (now - self._last_shower_detect) < timedelta(hours=1)
        if ah - low >= SHOWER_JUMP and not recently and not self.session:
            self._last_shower_detect = now
            return True
        return False

    async def _shower_event(self):
        now = dt_util.now()
        start_ah = min((v for _, v in self._ah_history), default=None)
        self._shower = {"at": now, "start_ah": start_ah, "vented": False}
        self._update_recommendation()
        if self.recommended_minutes <= 0:
            return
        # Nach dem Duschen zählt jede Minute – auch in der Ruhezeit, ohne Cooldown
        await self._send(
            f"Nach dem Duschen: {self.data[CONF_NAME]}",
            f"Jetzt lüften – {self.recommendation}",
            f"smart_ventilation_{self.entry.entry_id}_shower",
            targets=notify_util.filter_targets(self.hass, self.notify_targets, self.persons),
            category=CAT_SHOWER,
        )

    async def _shower_followup(self, now):
        if not self._shower or self.session:
            return
        if (now - self._shower["at"]) < timedelta(minutes=SHOWER_FOLLOWUP_MINUTES):
            return
        shower, self._shower = self._shower, None
        ah = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        still_humid = self.humidity_difference is not None and self.humidity_difference > DEFAULT_TARGET_DIFF
        if shower.get("start_ah") is not None and ah is not None:
            still_humid = still_humid and ah > shower["start_ah"] + 0.5
        if still_humid and not shower.get("vented"):
            await self._send(
                f"Noch feucht: {self.data[CONF_NAME]}",
                f"Seit dem Duschen wurde nicht gelüftet. {self.recommendation}",
                f"smart_ventilation_{self.entry.entry_id}_shower",
                targets=notify_util.filter_targets(self.hass, self.notify_targets, self.persons),
                category=CAT_SHOWER,
            )

    # ------------------------------------------------------------------
    # Urlaub
    # ------------------------------------------------------------------
    @property
    def on_vacation(self):
        entity_id = self.data.get(CONF_VACATION)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state not in ON_STATES:
            return False
        keyword = (self.data.get(CONF_VACATION_KEYWORD) or "").strip().lower()
        if keyword and entity_id.startswith("calendar."):
            return keyword in str(state.attributes.get("message", "")).lower()
        return True

    async def _vacation_mold_watch(self, now):
        if not self.on_vacation or self.mold_risk not in ("hoch", "kritisch"):
            return
        today = now.date().isoformat()
        if self._vacation_warned == today:
            return
        self._vacation_warned = today
        await self._send(
            f"Urlaub – Schimmelrisiko: {self.data[CONF_NAME]}",
            (
                f"Feuchte an der Wand {self.wall_rh:.0f} %. Wenn möglich lüften lassen "
                "oder den Luftentfeuchter einschalten."
            ),
            f"smart_ventilation_{self.entry.entry_id}_vacation",
            category=CAT_MOLD,
        )
        await self._save()

    # ------------------------------------------------------------------
    # Alle weg, Fenster offen
    # ------------------------------------------------------------------
    async def _left_with_window_open(self):
        open_now = self.open_windows()
        if not open_now or not self.persons or self.anyone_home:
            return
        names = ", ".join(
            (self.hass.states.get(w).attributes.get("friendly_name") or w) for w in open_now
        )
        await self._send(
            f"Fenster offen: {self.data[CONF_NAME]}",
            f"Niemand ist zu Hause, aber noch offen: {names}.",
            f"smart_ventilation_{self.entry.entry_id}_left",
            category=CAT_WARNING,
        )

    # ------------------------------------------------------------------
    # Sommer: Kühlen per Lüften
    # ------------------------------------------------------------------
    @property
    def comfort_temp(self):
        return float(self.data.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP))

    def cooling_minutes(self):
        """Minuten zum Abkühlen, 0 = nicht sinnvoll. Nur im Sommer, wenn draußen kühler und nicht viel feuchter."""
        if self.season != SEASON_SUMMER:
            return 0
        ti = _num_state(self.hass, self.data[CONF_INDOOR_TEMP])
        to = _num_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        ai = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        ao = _num_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        if None in (ti, to) or ti <= self.comfort_temp or to > ti - COOL_MIN_DIFF:
            return 0
        if ai is not None and ao is not None and ao > ai + COOL_MAX_EXTRA_HUMIDITY:
            return 0
        wind, angle, temp_diff = self._context()
        # cross mitgeben wie bei der normalen Lüftungsempfehlung (_update_recommendation) - sonst
        # würde hier immer der nicht-Querlüften-Bucket abgefragt, obwohl bei zwei Fenstern
        # tatsächlich (und beim Lernen genauso) quergelüftet wird, und das gelernte Modell für
        # diesen Raum bliebe für Kühlen/Vorheizen dauerhaft ungenutzt.
        cross = len(self.windows) >= 2
        n, _ = self._model_ach(wind, angle, temp_diff, cross)
        target = max(self.comfort_temp, to + 0.5)
        return max(10, min(60, -60 / n * math.log((target - to) / (ti - to)) if ti > target else 10))

    # ------------------------------------------------------------------
    # Vorheizen per Lüften (nach kalter Nacht wärmere Luft tagsüber nutzen)
    # ------------------------------------------------------------------
    @property
    def preheat_temp(self):
        return float(self.data.get(CONF_PREHEAT_TEMP, DEFAULT_PREHEAT_TEMP))

    def preheat_minutes(self):
        """Minuten zum Vorheizen, 0 = nicht sinnvoll.

        Soll ausdrücklich nur in der Heizsaison passieren, nicht im echten Sommer unnötig Wärme
        reinholen. Dafür zählt aber nicht die automatisch ERKANNTE Saison (self.season) - die
        reagiert seit 2.3.19 bewusst erst nach mehreren Stunden Trend, damit sie nicht flackert,
        und kann in der Übergangszeit deshalb tagelang "Sommer" anzeigen, obwohl es nachts schon
        klar unter die Heizgrenze fällt. Genau an solchen milden Herbst-/Frühlingstagen soll
        Vorheizen ja funktionieren. Blockiert wird daher nur, wenn EXPLIZIT "Sommer" eingestellt
        ist (nicht "Automatisch") - dann hat der Nutzer bewusst gesagt, dass hier keine Heizung
        /kein Vorheizen gebraucht wird. Die eigentliche fachliche Voraussetzung bleibt die
        Nacht-Tiefsttemperatur: nur nach einer Nacht mit Tiefstwerten unter der Heizgrenze (sonst
        macht das Vorziehen der Heizung keinen Sinn) und nur, wenn draußen jetzt spürbar wärmer
        ist als drinnen und der Raum noch unter der Vorheiz-Schwelle liegt. Droht laut Vorhersage
        in Kürze Regen, lohnt sich das Öffnen nicht – auch wenn es gerade noch trocken ist. Ist die
        Luft draußen deutlich feuchter als drinnen, würde man sich mit dem Vorheizen zugleich ein
        Feuchteproblem einhandeln – dann lohnt es sich trotz der Wärme nicht (siehe
        COOL_MAX_EXTRA_HUMIDITY, spiegelbildlich für Vorheizen).
        """
        if self.data.get(CONF_SEASON_MODE, DEFAULT_SEASON_MODE) == SEASON_SUMMER:
            return 0
        threshold = float(self.data.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD))
        if self._last_night_low is None or self._last_night_low >= threshold:
            return 0
        if self._rain_soon:
            return 0
        ti = _num_state(self.hass, self.data[CONF_INDOOR_TEMP])
        to = _num_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if None in (ti, to) or ti >= self.preheat_temp or to < ti + PREHEAT_MIN_WARMER:
            return 0
        ai = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        ao = _num_state(self.hass, self.data[CONF_OUTDOOR_HUMIDITY])
        if ai is not None and ao is not None and ao > ai + PREHEAT_MAX_EXTRA_HUMIDITY:
            return 0
        wind, angle, temp_diff = self._context()
        # cross mitgeben - siehe Kommentar in cooling_minutes() weiter oben.
        cross = len(self.windows) >= 2
        n, _ = self._model_ach(wind, angle, temp_diff, cross)
        target = min(self.preheat_temp, to - 0.5)
        return max(10, min(60, -60 / n * math.log((to - target) / (to - ti)) if ti < target else 10))

    def preheat_plan(self, forecast):
        """Aus der Stundenvorhersage: ab wann es heute/morgen warm genug zum Vorheizen wird,
        bis wann noch – nur wenn die Nacht-Voraussetzung (kalte Nacht) bereits erfüllt ist.
        Blockiert nur bei explizit eingestelltem Sommer-Modus, siehe preheat_minutes()."""
        if self.data.get(CONF_SEASON_MODE, DEFAULT_SEASON_MODE) == SEASON_SUMMER:
            return None
        ti = _num_state(self.hass, self.data[CONF_INDOOR_TEMP])
        threshold = float(self.data.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD))
        if (
            ti is None
            or ti >= self.preheat_temp
            or self._last_night_low is None
            or self._last_night_low >= threshold
        ):
            return None
        now = dt_util.now()
        start = end = None
        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            temp = item.get("temperature")
            if when is None or temp is None:
                continue
            when = dt_util.as_local(when)
            if when < now - timedelta(minutes=30) or when > now + timedelta(hours=24):
                continue
            rain = item.get("precipitation") or 0.0
            rain_prob = item.get("precipitation_probability") or 0.0
            warm = (
                float(temp) >= ti + PREHEAT_MIN_WARMER
                and rain <= FORECAST_MAX_RAIN_MM
                and rain_prob < FORECAST_MAX_RAIN_PROB
                and self._forecast_wind_factor(item) >= MIN_FORECAST_WIND_FACTOR
            )
            if start is None and warm:
                start = when
            elif start is not None and not warm:
                end = when
                break
        if start is None:
            return None
        day = "Heute" if start.date() == now.date() else "Morgen"
        text = f"{day} ab {start.strftime('%H:%M')}"
        return f"{text} bis {end.strftime('%H:%M')} Uhr" if end else f"{text} Uhr"

    def cooling_plan(self, forecast):
        """Aus der Stundenvorhersage: ab wann abends kühler, bis wann morgens noch kühl."""
        ti = _num_state(self.hass, self.data[CONF_INDOOR_TEMP])
        if self.season != SEASON_SUMMER or ti is None or ti <= self.comfort_temp:
            return None
        now = dt_util.now()
        start = end = None
        for item in forecast:
            when = dt_util.parse_datetime(str(item.get("datetime", "")))
            temp = item.get("temperature")
            if when is None or temp is None:
                continue
            when = dt_util.as_local(when)
            if when < now - timedelta(minutes=30) or when > now + timedelta(hours=24):
                continue
            cool = (
                float(temp) <= ti - COOL_MIN_DIFF
                and self._forecast_wind_factor(item) >= MIN_FORECAST_WIND_FACTOR
            )
            if start is None and cool:
                start = when
            elif start is not None and not cool:
                end = when
                break
        if start is None:
            return None
        day = "Heute" if start.date() == now.date() else "Morgen"
        text = f"{day} ab {start.strftime('%H:%M')}"
        return f"{text} bis {end.strftime('%H:%M')} Uhr" if end else f"{text} Uhr"

    async def _warm_outside_warning(self):
        """Ans Schließen erinnern, wenn das Lüften den Raum aufheizt – unabhängig von der
        Jahreszeit (an milden Wintertagen kann es genauso vorkommen).

        Dieselbe Grenze wie bei der Empfehlung, sonst widersprechen sich „Lüften“ und „Schließen“:
        - zum Kühlen gelüftet: sobald draußen wärmer als drinnen (Kühlen klappt nicht mehr)
        - wegen Feuchte/CO₂ gelüftet: erst ab der eingestellten Grenze
        - zum Vorheizen gelüftet: gar nicht - die Wärme ist hier ja gerade das Ziel
        """
        if not self.session or self._warm_warned or self.session.get("preheat"):
            return
        ti = _num_state(self.hass, self.data[CONF_INDOOR_TEMP])
        to = _num_state(self.hass, self.data[CONF_OUTDOOR_TEMP])
        if ti is None or to is None:
            return
        limit = 0.5 if self.session.get("cooling") else float(
            self.data.get(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)
        )
        if to - ti <= limit:
            return
        self._warm_warned = True
        await self._send(
            f"Fenster schließen: {self.data[CONF_NAME]}",
            f"Draußen ist es jetzt {to - ti:.1f} °C wärmer ({to:.1f} °C) als drinnen ({ti:.1f} °C) – "
            "der Raum heizt sich sonst auf.",
            f"smart_ventilation_{self.entry.entry_id}_warm",
            category=CAT_WARNING,
        )

    # ------------------------------------------------------------------
    # Luftentfeuchter
    # ------------------------------------------------------------------
    def _ventilation_priority_active(self, now=None):
        """True, wenn Lüften gegenüber dem Entfeuchter Vorrang hat."""
        if self.session or self.open_windows():
            return True
        if self.recommended_minutes <= 0:
            return False
        if self.block_reason in ("Regen", "Gewitter erwartet", "Außenluft nicht trockener"):
            return False
        if now is not None and self.in_quiet_hours(now):
            return False
        if self.on_vacation or (self.persons and not self.anyone_home):
            return False
        return True

    async def _dehumidifier_control(self, now):
        entity_id = self.data.get(CONF_DEHUMIDIFIER)
        if not entity_id:
            return
        domain = entity_id.partition(".")[0]
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return

        rh = self.indoor_rh
        indoor_ah = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        target_abs = float(self.data.get(CONF_TARGET_ABS, 11.5))
        ah_start = target_abs + DEHUM_AH_HYSTERESIS
        ah_stop = target_abs - DEHUM_AH_HYSTERESIS
        rh_start = DEHUM_ON_RH
        rh_stop = DEHUM_OFF_RH - DEHUM_RH_HYSTERESIS
        mold_high = self.mold_risk == "hoch"
        need = (
            (indoor_ah is not None and indoor_ah > ah_start)
            or (rh is not None and rh >= rh_start)
            or self.mold_risk in ("erhöht", "hoch")
        )

        humidity_difference = self.humidity_difference
        ventilation_available = self._ventilation_priority_active(now) and not self.open_windows()
        cannot_vent = (
            _is_raining(self.hass, self.data.get(CONF_RAIN))
            or (humidity_difference is not None and humidity_difference <= 1.0)
            or self.in_quiet_hours(now)
            or self.on_vacation
            or (self.persons and not self.anyone_home)
            or not ventilation_available
        )

        if self._dehum_on_since is None:
            if (
                need
                and cannot_vent
                and not ventilation_available
                and not self.open_windows()
                and not self.session
                and (self._dehum_off_until is None or now >= self._dehum_off_until or mold_high)
                and state.state == "off"
            ):
                self._dehum_on_since = now
                if await self._call(domain, "turn_on", {"entity_id": entity_id}):
                    await self._save()
                else:
                    self._dehum_on_since = None
            elif state.state == "on":
                self._dehum_on_since = now
                await self._save()
            return

        ran = (now - self._dehum_on_since) >= timedelta(minutes=DEHUM_MIN_RUNTIME_MINUTES)
        done_ah = indoor_ah is not None and indoor_ah <= ah_stop
        done_rh = rh is not None and rh <= rh_stop
        done = done_ah or (indoor_ah is None and done_rh)
        stop_for_ventilation = self.open_windows() or ventilation_available

        if stop_for_ventilation or (ran and (done or not need)):
            await self._call(domain, "turn_off", {"entity_id": entity_id})
            self._dehum_on_since = None
            self._dehum_off_until = now + timedelta(minutes=DEHUM_RESTART_COOLDOWN_MINUTES)
            await self._save()
        elif state.state == "off":
            self._dehum_on_since = None
            await self._save()

    @property
    def dehumidifier_active(self):
        """True, wenn der Entfeuchter läuft oder die Automatik ihn aktuell anfordert.
        
        Der Status darf nicht davon abhängen, ob der nächste 30-s-Steuertakt bereits
        gelaufen ist. So bleibt die Raumübersicht auch direkt nach einer relevanten
        Sensoränderung konsistent.
        """
        if self._dehum_on_since is not None:
            return True

        entity_id = self.data.get(CONF_DEHUMIDIFIER)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unavailable", "unknown"):
            return False
        if state.state == "on":
            return True

        indoor_ah = _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
        target_abs = float(self.data.get(CONF_TARGET_ABS, 11.5))
        rh = self.indoor_rh
        need = (
            indoor_ah is not None and indoor_ah > target_abs
        ) or (
            rh is not None and rh >= DEHUM_ON_RH
        ) or self.mold_risk in ("erhöht", "hoch")
        humidity_difference = self.humidity_difference
        cannot_vent = (
            _is_raining(self.hass, self.data.get(CONF_RAIN))
            or (
                humidity_difference is not None
                and humidity_difference <= 1.0
            )
            or self.in_quiet_hours()
            or self.on_vacation
            or (self.persons and not self.anyone_home)
        )
        return bool(
            state.state == "off"
            and need
            and cannot_vent
            and not self.open_windows()
        )

    # ------------------------------------------------------------------
    # Rollo/Jalousie
    # ------------------------------------------------------------------
    async def _shutter_control(self, now):
        entity_id = self.data.get(CONF_SHUTTER)
        if not entity_id:
            return
        domain = entity_id.partition(".")[0]
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        need = self.shutter_recommended
        radiation = _num_state(self.hass, self.data.get(CONF_SOLAR_RADIATION))

        if self._shutter_closed_since is not None and radiation is not None:
            # Hysterese: ein bereits geschlossenes Rollo bleibt bei kurzzeitiger
            # Einstrahlungsschwankung geschlossen, bis die Strahlung klar abgefallen ist.
            if SOLAR_RADIATION_MIN <= radiation < SOLAR_RADIATION_RELEASE and self.season == SEASON_SUMMER:
                need = True

        if self._shutter_closed_since is None:
            # Schließen: nur ein tatsächlich offenes Rollo anfassen - eine manuell gewählte
            # Zwischenposition (z. B. teilweise geschlossen) wird nicht überschrieben, und ein
            # bereits von Hand geschlossenes Rollo übernehmen wir nicht in unsere Steuerung (siehe
            # dasselbe Prinzip beim Entfeuchter: nur verwalten, was WIR selbst gestartet haben).
            if need and state.state == "open":
                if await self._call(domain, "close_cover", {"entity_id": entity_id}):
                    self._shutter_closed_since = now
                    await self._save()
            return

        # Öffnen: erst nach Mindestlaufzeit und sobald keine direkte Sonne mehr am Fenster
        # anliegt - vermeidet ständiges Auf/Zu, wenn die Sonne kurz hinter einer Wolke
        # verschwindet oder genau an der Winkel-Schwelle entlangwandert.
        ran = (now - self._shutter_closed_since) >= timedelta(minutes=SHUTTER_MIN_RUNTIME_MINUTES)
        if ran and not need:
            await self._call(domain, "open_cover", {"entity_id": entity_id})
            self._shutter_closed_since = None
            await self._save()

    @property
    def shutter_closed(self):
        return self._shutter_closed_since is not None

    async def _shutter_notify(self, was_closed):
        """Push-Benachrichtigungen zur Rollo-Empfehlung: einmalig beim Beginn direkter Sonne
        (schließen) und einmalig, sobald sie vorbei ist (öffnen) - jeweils einmal pro
        zusammenhängendem Expositionsfenster, nicht bei jedem 30-s-Tick.

        was_closed: Rollo-Status VOR dem _shutter_control()-Aufruf in diesem Tick - damit lässt
        sich erkennen, ob gerade in diesem Tick automatisch wieder geöffnet wurde.
        """
        name = self.data[CONF_NAME]
        tag = f"smart_ventilation_{self.entry.entry_id}_shutter"

        if self.shutter_recommended:
            if not self._shutter_notified:
                self._shutter_notified = True
                await self._save()
                if self.shutter_closed:
                    title = f"Rollo geschlossen: {name}"
                    message = "Direkte Sonne am Fenster – das Rollo wurde automatisch geschlossen."
                else:
                    title = f"Rollo schließen: {name}"
                    message = (
                        "Direkte Sonne am Fenster – am besten Rollo/Jalousie schließen, damit "
                        "sich der Raum nicht aufheizt."
                    )
                await self._send(title, message, tag, category=CAT_WARNING)
            return

        if self._shutter_notified:
            self._shutter_notified = False
            await self._save()
            if not self.data.get(CONF_SHUTTER):
                # Reine Empfehlung ohne hinterlegtes Rollo-Entity: sofort informieren, sobald
                # keine direkte Sonne mehr anliegt - es gibt hier keine Automatik, die das später
                # übernehmen würde.
                await self._send(
                    f"Rollo öffnen: {name}",
                    "Keine direkte Sonne mehr am Fenster – Rollo/Jalousie kann wieder geöffnet "
                    "werden.",
                    tag, category=CAT_WARNING,
                )

        if was_closed and not self.shutter_closed:
            # Mit hinterlegtem Entity: erst benachrichtigen, wenn _shutter_control es (nach der
            # Mindestlaufzeit) tatsächlich wieder geöffnet hat - nicht schon, sobald die direkte
            # Sonne vorbei ist, sonst würde die Meldung der echten Aktion vorauseilen.
            await self._send(
                f"Rollo geöffnet: {name}",
                "Keine direkte Sonne mehr am Fenster – das Rollo wurde automatisch wieder "
                "geöffnet.",
                tag, category=CAT_WARNING,
            )

    # ------------------------------------------------------------------
    # Wochenbericht
    # ------------------------------------------------------------------
    def _track_mold_day(self, now):
        if self.mold_risk in ("hoch", "erhöht"):
            days = self.stats["week"].setdefault("mold_days", [])
            today = now.date().isoformat()
            if today not in days:
                days.append(today)

    def weekly_summary(self):
        week = self.period_stats("week")
        mold_days = len(self.stats["week"].get("mold_days", []))
        return {
            "raum": self.data.get(CONF_NAME),
            "anzahl": week["count"],
            "erfolgreich": week["ok"],
            "minuten": week["minutes"],
            "kwh": week["kwh"],
            "kosten": week["cost"],
            "kwh_gespart": week["kwh_gespart"],
            "kosten_gespart": week["kosten_gespart"],
            "schimmeltage": mold_days,
        }

    def report_due(self, now, last_report):
        return (
            now.weekday() == REPORT_WEEKDAY
            and now.hour >= REPORT_HOUR
            and last_report != _week_key(now)
        )

    async def _weekly_report(self, now):
        if not self.data.get(CONF_WEEKLY_REPORT) or not self.report_due(now, self._last_report):
            return
        self._last_report = _week_key(now)
        await self._save()
        if self._report_by_overview():
            return
        s = self.weekly_summary()
        mold = (
            f"Schimmelrisiko an {s['schimmeltage']} {'Tag' if s['schimmeltage'] == 1 else 'Tagen'} erhöht."
            if s["schimmeltage"] else "Schimmelrisiko die ganze Woche niedrig."
        )
        savings = (
            f" Durch Vorheizen ca. {de_num(s['kwh_gespart'], 1)} kWh ≈ {de_num(s['kosten_gespart'], 2)} € gespart."
            if s["kwh_gespart"] > 0 else ""
        )
        await self._send(
            f"Wochenbericht: {s['raum']}",
            (
                f"{s['anzahl']}× gelüftet ({s['erfolgreich']} erfolgreich), {s['minuten']:.0f} Min., "
                f"{de_num(s['kwh'], 1)} kWh ≈ {de_num(s['kosten'], 2)} €. {mold}{savings}"
            ),
            f"smart_ventilation_{self.entry.entry_id}_report",
            category=CAT_REPORT,
        )

    def _report_by_overview(self):
        for other in self.hass.data.get(DOMAIN, {}).values():
            if getattr(other, "is_overview", False) and other.weekly_report:
                return True
        return False

    # ------------------------------------------------------------------
    # Einstieg aus dem 30-s-Takt
    # ------------------------------------------------------------------
    async def _extras_tick(self):
        now = dt_util.now()
        if self._detect_humidity_jump(now):
            await self._shower_event()
        if self.session:
            self._trace_add()
            if self._shower:
                self._shower["vented"] = True
            await self._warm_outside_warning()
        await self._shower_followup(now)
        await self._vacation_mold_watch(now)

        # Zentrale Priorität der Zusatzsteuerungen:
        # 1. Aktive Lüftung hat Vorrang – kein Entfeuchter parallel.
        # 2. Wenn Lüften möglich ist, soll zuerst gelüftet werden.
        # 3. Der Entfeuchter darf nur als Ausweichlösung übernehmen.
        # 4. Das Rollo bleibt unabhängig davon sicherheitsorientiert.
        if self.session or self.open_windows():
            # Bei aktiver/manueller Lüftung darf die Entfeuchter-Automatik nicht
            # neu starten. Eine bereits laufende Automatik wird durch
            # _dehumidifier_control beendet.
            await self._dehumidifier_control(now)
        else:
            await self._dehumidifier_control(now)

        was_shutter_closed = self.shutter_closed
        await self._shutter_control(now)
        await self._shutter_notify(was_shutter_closed)
        self._track_mold_day(now)
        await self._weekly_report(now)