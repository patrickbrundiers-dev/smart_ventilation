"""Schimmel-Frühwarnung über mehrere Tage sowie Monats- und Jahresvergleich (Mixin der Raum-Logik)."""
from __future__ import annotations

from datetime import date, timedelta

from homeassistant.util import dt as dt_util

from .const import (
    ANOMALY_BASELINE_DAYS, ANOMALY_FACTOR, ANOMALY_MIN_MINUTES, ANOMALY_MIN_SAMPLE_DAYS,
    CAT_MOLD, CAT_REPORT, CAT_WARNING, CONF_MONTHLY_REPORT, CONF_NAME, DAY_LOG_DAYS, DOMAIN,
    HISTORY_MONTHS, MOLD_CRITICAL_MINUTES, MOLD_LOG_DAYS, MOLD_REWARN_DAYS, MOLD_RH_HIGH,
    MOLD_STREAK_WARN, MONTHLY_REPORT_HOUR,
)
from . import notify_util

MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]
MAX_STEP_MINUTES = 10  # Lücken (z. B. Neustart) nicht voll mitzählen


def month_name(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def previous_month(key: str) -> str:
    year, month = (int(x) for x in key.split("-"))
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def change_percent(new, old):
    if not old:
        return None
    return round((new - old) / old * 100)


def de(value, digits=1):
    return f"{value:.{digits}f}".replace(".", ",")


class HistoryMixin:
    """Erwartet die Attribute/Methoden des SmartVentilationCoordinator."""

    def _init_history(self):
        self.mold_log = {}            # {"2026-12-05": Minuten mit Wandfeuchte ≥ 80 %}
        self.history = {}             # {"2026-11": {...Monatswerte...}}
        self.day_log = {}             # {"2026-09-20": {...Tageswerte für die Karten-Sparkline...}}
        self._mold_warned = None      # {"start": Beginn der Serie, "on": Datum der Warnung}
        self._mold_pending = False
        self._last_month_report = None
        self._last_measure = None
        self._last_anomaly_check = None  # zuletzt auf Anomalie geprüfter Tag (der Vortag)

    def _history_store(self):
        return {
            "mold_log": self.mold_log,
            "history": self.history,
            "day_log": self.day_log,
            "mold_warned": self._mold_warned,
            "last_month_report": self._last_month_report,
            "last_anomaly_check": self._last_anomaly_check.isoformat() if self._last_anomaly_check else None,
        }

    def _history_load(self, stored):
        self.mold_log = stored.get("mold_log") or {}
        self.history = stored.get("history") or {}
        self.day_log = stored.get("day_log") or {}
        self._mold_warned = stored.get("mold_warned")
        self._last_month_report = stored.get("last_month_report")
        if stored.get("last_anomaly_check"):
            try:
                self._last_anomaly_check = date.fromisoformat(stored["last_anomaly_check"])
            except ValueError:
                self._last_anomaly_check = None

    # ------------------------------------------------------------------
    # Messen (alle 30 s)
    # ------------------------------------------------------------------
    def _measure(self, now):
        """Kritische Wand-Minuten und Lüftungsbedarf aufsummieren."""
        step = 0.5
        if self._last_measure is not None:
            step = min((now - self._last_measure).total_seconds() / 60, MAX_STEP_MINUTES)
        self._last_measure = now
        if step <= 0:
            return

        wall = self.wall_rh
        if wall is not None and wall >= MOLD_RH_HIGH:
            today = now.date().isoformat()
            self.mold_log[today] = round(self.mold_log.get(today, 0) + step, 1)

        if self.recommended_minutes > 0:
            for period in ("day", "week", "month", "total"):
                p = self.stats[period]
                p["need_minutes"] = p.get("need_minutes", 0.0) + step

        cutoff = (now.date() - timedelta(days=MOLD_LOG_DAYS)).isoformat()
        for day in [d for d in self.mold_log if d < cutoff]:
            del self.mold_log[day]

    # ------------------------------------------------------------------
    # Schimmel-Frühwarnung
    # ------------------------------------------------------------------
    def _critical(self, day: date) -> bool:
        return self.mold_log.get(day.isoformat(), 0) >= MOLD_CRITICAL_MINUTES

    def mold_streak(self, today=None):
        """(Anzahl kritischer Tage in Folge bis gestern, erster Tag der Serie)."""
        today = today or dt_util.now().date()
        day, count = today - timedelta(days=1), 0
        while self._critical(day):
            count += 1
            day -= timedelta(days=1)
        return count, (day + timedelta(days=1)) if count else None

    @property
    def mold_hours_today(self):
        return round(self.mold_log.get(dt_util.now().date().isoformat(), 0) / 60, 1)

    @property
    def mold_alarm(self):
        return self.mold_streak()[0] >= MOLD_STREAK_WARN

    async def _mold_early_warning(self, now):
        streak, start = self.mold_streak(now.date())
        if streak < MOLD_STREAK_WARN:
            return
        warned = self._mold_warned or {}
        same_series = warned.get("start") == start.isoformat()
        if same_series and (now.date() - date.fromisoformat(warned["on"])).days < MOLD_REWARN_DAYS:
            return
        if self.in_quiet_hours(now):
            return  # nach der Ruhezeit nachholen
        previous_warned = self._mold_warned
        self._mold_warned = {"start": start.isoformat(), "on": now.date().isoformat()}
        await self._save()
        hours = [self.mold_log.get((now.date() - timedelta(days=i)).isoformat(), 0) / 60 for i in range(1, streak + 1)]
        sent = await self._send(
            f"Schimmelgefahr: {self.data[CONF_NAME]}",
            (
                f"Seit {streak} Tagen ist die Wand täglich rund {de(sum(hours) / len(hours), 0)} Stunden "
                "feuchter als 80 % – dann kann Schimmel wachsen. Tipps: mehrmals täglich kurz stoßlüften, "
                "den Raum nicht unter 18 °C auskühlen lassen und Möbel ein paar Zentimeter von Außenwänden abrücken."
            ),
            f"smart_ventilation_{self.entry.entry_id}_mold",
            category=CAT_MOLD,
        )
        if not sent:
            # Kein Ziel erreichbar - nicht als "gewarnt" merken, sonst käme frühestens erst nach
            # MOLD_REWARN_DAYS wieder eine Warnung, obwohl nie tatsächlich eine ankam.
            self._mold_warned = previous_warned
            await self._save()

    # ------------------------------------------------------------------
    # Monatsarchiv und -vergleich
    # ------------------------------------------------------------------
    def _archive_month(self, old_period):
        """Beim Monatswechsel: abgelaufenen Monat ins Archiv."""
        key = old_period.get("key")
        if not key or key == "total":
            return
        critical = sum(1 for d, m in self.mold_log.items() if d.startswith(key) and m >= MOLD_CRITICAL_MINUTES)
        kwh = old_period.get("kwh", 0.0)
        self.history[key] = {
            "lueftungen": old_period.get("count", 0),
            "erfolgreich": old_period.get("ok", 0),
            "minuten": round(old_period.get("seconds", 0.0) / 60),
            "bedarf_h": round(old_period.get("need_minutes", 0.0) / 60, 1),
            "kwh": round(kwh, 2),
            "kosten": round(kwh * self.energy_price, 2),
            "schimmeltage": critical,
        }
        for old in sorted(self.history)[:-HISTORY_MONTHS]:
            del self.history[old]

    def _archive_day(self, old_period):
        """Beim Tageswechsel: abgelaufenen Tag fürs Sparkline-Diagramm der Karte archivieren."""
        key = old_period.get("key")
        if not key:
            return
        kwh = old_period.get("kwh", 0.0)
        kwh_saved = old_period.get("kwh_gespart", 0.0)
        self.day_log[key] = {
            "anzahl": old_period.get("ok", 0),
            "minuten": round(old_period.get("seconds", 0.0) / 60),
            "kwh": round(kwh, 2),
            "kosten": round(kwh * self.energy_price, 2),
            "kwh_netto": round(kwh - kwh_saved, 2),
            "kosten_netto": round((kwh - kwh_saved) * self.energy_price, 2),
        }
        cutoff = (dt_util.now().date() - timedelta(days=DAY_LOG_DAYS)).isoformat()
        for day in [d for d in self.day_log if d < cutoff]:
            del self.day_log[day]

    def day_trend(self, days=7):
        """Die letzten `days` Tage (älteste zuerst) für die Sparkline auf der Karte -
        vergangene Tage aus dem Archiv, der heutige live aus den laufenden Tagesstatistiken."""
        today = dt_util.now().date()
        out = []
        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            key = day.isoformat()
            if i == 0:
                s = self.period_stats("day")
                out.append({
                    "datum": key, "anzahl": s["ok"], "kwh": s["kwh"], "kosten": s["cost"],
                    "kwh_netto": round(s["kwh"] - s["kwh_gespart"], 2),
                    "kosten_netto": round(s["cost"] - s["kosten_gespart"], 2),
                })
            else:
                entry = self.day_log.get(key, {})
                out.append({
                    "datum": key,
                    "anzahl": entry.get("anzahl", 0),
                    "kwh": entry.get("kwh", 0.0),
                    "kosten": entry.get("kosten", 0.0),
                    "kwh_netto": entry.get("kwh_netto", 0.0),
                    "kosten_netto": entry.get("kosten_netto", 0.0),
                })
        return out

    def _day_anomaly(self, day: date):
        """Vergleicht die Lüftungsminuten eines abgeschlossenen Tages mit dem Schnitt der Tage
        davor - deutlich mehr als sonst kann auf ein vergessenes offenes Fenster, einen
        defekten Sensor oder tatsächlich mehr Bedarf (Besuch, Wäsche trocknen) hindeuten."""
        entry = self.day_log.get(day.isoformat())
        if not entry:
            return None
        minutes = entry.get("minuten", 0)
        if minutes < ANOMALY_MIN_MINUTES:
            return None
        cutoff = (day - timedelta(days=ANOMALY_BASELINE_DAYS)).isoformat()
        baseline = [
            v["minuten"] for k, v in self.day_log.items()
            if cutoff <= k < day.isoformat()
        ]
        if len(baseline) < ANOMALY_MIN_SAMPLE_DAYS:
            return None
        avg = sum(baseline) / len(baseline)
        if avg <= 0 or minutes < avg * ANOMALY_FACTOR:
            return None
        return minutes, avg

    async def _anomaly_check(self, now):
        yesterday = now.date() - timedelta(days=1)
        if self._last_anomaly_check == yesterday or yesterday.isoformat() not in self.day_log:
            return
        if self.in_quiet_hours(now):
            return  # nach der Ruhezeit nachholen
        self._last_anomaly_check = yesterday
        await self._save()
        result = self._day_anomaly(yesterday)
        if not result:
            return
        minutes, avg = result
        sent = await self._send(
            f"Ungewöhnlich viel Lüftungsbedarf: {self.data[CONF_NAME]}",
            (
                f"Gestern wurde {de(minutes / 60, 1)} Stunden gelüftet – deutlich mehr als im "
                f"Schnitt der letzten Tage ({de(avg / 60, 1)} Std.). Mögliche Ursache: ein "
                "Fenster war länger offen als gedacht, ein Sensor liefert falsche Werte, oder "
                "es gab tatsächlich mehr Bedarf (z. B. Besuch, Wäsche trocknen)."
            ),
            f"smart_ventilation_{self.entry.entry_id}_anomaly",
            category=CAT_WARNING,
        )
        if not sent:
            # Kein Ziel erreichbar - "gestern" nicht als geprüft verbuchen, sonst gibt es für
            # diesen Tag nie wieder eine Chance auf die Warnung (der nächste Tick prüft bereits
            # den nächsten Tag).
            self._last_anomaly_check = None
            await self._save()

    def month_comparison(self):
        """Letzter abgeschlossener Monat im Vergleich zum Vormonat und zum Vorjahr."""
        if not self.history:
            return None
        last = sorted(self.history)[-1]
        cur = self.history[last]
        prev = self.history.get(previous_month(last))
        year, month = last.split("-")
        ly = self.history.get(f"{int(year) - 1}-{month}")
        return {
            "monat": month_name(last),
            **cur,
            "vormonat": ({"monat": month_name(previous_month(last)), **prev} if prev else None),
            "bedarf_vs_vormonat_prozent": change_percent(cur["bedarf_h"], prev["bedarf_h"]) if prev else None,
            "vorjahr": ({"monat": month_name(f"{int(year) - 1}-{month}"), **ly} if ly else None),
            "bedarf_vs_vorjahr_prozent": change_percent(cur["bedarf_h"], ly["bedarf_h"]) if ly else None,
        }

    @property
    def need_hours_month(self):
        return round(self.period_stats("month").get("need_hours", 0.0), 1)

    def monthly_text(self):
        c = self.month_comparison()
        if not c:
            return None
        text = (
            f"{c['monat']}: {c['lueftungen']}× gelüftet ({c['erfolgreich']} erfolgreich), "
            f"Lüftungsbedarf {de(c['bedarf_h'])} h, {de(c['kwh'])} kWh ≈ {de(c['kosten'], 2)} €."
        )
        if c["bedarf_vs_vormonat_prozent"] is not None:
            p = c["bedarf_vs_vormonat_prozent"]
            text += f" {abs(p)} % {'mehr' if p > 0 else 'weniger'} Bedarf als im {c['vormonat']['monat'].split()[0]}." if p else " Bedarf wie im Vormonat."
        if c["bedarf_vs_vorjahr_prozent"] is not None:
            p = c["bedarf_vs_vorjahr_prozent"]
            text += f" Gegenüber dem Vorjahr {abs(p)} % {'mehr' if p > 0 else 'weniger'}." if p else ""
        if c["schimmeltage"]:
            text += f" {c['schimmeltage']} kritische Schimmeltage."
        return text

    def _monthly_due(self, now, last_sent):
        if now.day != 1 or now.hour < MONTHLY_REPORT_HOUR or not self.history:
            return False
        return last_sent != sorted(self.history)[-1]

    async def _monthly_report(self, now):
        if not self.data.get(CONF_MONTHLY_REPORT) or not self._monthly_due(now, self._last_month_report):
            return
        self._last_month_report = sorted(self.history)[-1]
        await self._save()
        if self._monthly_by_overview():
            return
        text = self.monthly_text()
        if text:
            await self._send(
                f"Monatsbericht: {self.data[CONF_NAME]}", text,
                f"smart_ventilation_{self.entry.entry_id}_month",
                category=CAT_REPORT,
            )

    def _monthly_by_overview(self):
        for other in self.hass.data.get(DOMAIN, {}).values():
            if getattr(other, "is_overview", False) and other.monthly_report:
                return True
        return False

    async def _history_tick(self, now):
        self._measure(now)
        await self._mold_early_warning(now)
        await self._monthly_report(now)
        await self._anomaly_check(now)
