"""HA-independent Schimmelrisiko-Bewertung.

Die Schwellenwerte orientieren sich an den UBA-Hinweisen:
- Raumluft dauerhaft <= 65–70 % RH
- Material-/Wandoberfläche < 80 % RH
- Kondensation ist besonders kritisch

Die Berechnung ist eine konservative Frühwarnung, keine Bauwerksdiagnose.
"""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    MOLD_DEWPOINT_MARGIN_CRITICAL, MOLD_RH_CRITICAL, MOLD_RH_ELEVATED,
    MOLD_RH_HIGH, MOLD_RH_WATCH, MOLD_TREND_WARN_RH_PER_HOUR,
)


@dataclass(frozen=True)
class MoldAssessment:
    level: str
    reason: str
    action: str
    wall_rh: float | None
    wall_temperature: float | None
    dew_point_margin: float | None
    duration_hours: float
    trend_rh_per_hour: float | None

    @property
    def score(self) -> int:
        base = {"unbekannt": 0, "niedrig": 10, "beobachten": 30, "erhöht": 50, "hoch": 72, "kritisch": 92}.get(self.level, 0)
        score = float(base)
        if self.dew_point_margin is not None and self.dew_point_margin <= MOLD_DEWPOINT_MARGIN_CRITICAL:
            score = max(score, 95)
        elif self.dew_point_margin is not None and self.dew_point_margin < 2.0:
            score += (2.0 - max(0.0, self.dew_point_margin)) * 6.0
        if self.trend_rh_per_hour is not None and self.trend_rh_per_hour >= MOLD_TREND_WARN_RH_PER_HOUR:
            score += min(8.0, self.trend_rh_per_hour - MOLD_TREND_WARN_RH_PER_HOUR + 2.0)
        if self.duration_hours >= 6:
            score += 5
        return max(0, min(100, round(score)))


def assess_mold_risk(
    wall_rh: float | None,
    wall_temperature: float | None,
    indoor_rh: float | None,
    dew_point: float | None,
    duration_high_minutes: float = 0.0,
    duration_elevated_minutes: float = 0.0,
    trend_rh_per_hour: float | None = None,
) -> MoldAssessment:
    if wall_rh is None:
        if indoor_rh is None:
            return MoldAssessment(
                "unbekannt",
                "Feuchtedaten fehlen",
                "Sensorwerte prüfen",
                None,
                wall_temperature,
                None,
                max(0.0, duration_high_minutes) / 60,
                trend_rh_per_hour,
            )
        margin = None if dew_point is None or wall_temperature is None else wall_temperature - dew_point
        if margin is not None and margin <= MOLD_DEWPOINT_MARGIN_CRITICAL:
            return MoldAssessment(
                "kritisch",
                "Taupunkt liegt sehr nah an der Raumluft",
                "Sofort Feuchte abführen und Raum ausreichend warm halten",
                None,
                wall_temperature,
                margin,
                max(0.0, duration_high_minutes) / 60,
                trend_rh_per_hour,
            )
        if indoor_rh >= MOLD_RH_HIGH - 5:
            return MoldAssessment(
                "hoch",
                "Raumluftfeuchte über 75 % – Wanddaten fehlen",
                "Jetzt stoßlüften und Wanddaten wiederherstellen",
                None,
                wall_temperature,
                margin,
                max(0.0, duration_high_minutes) / 60,
                trend_rh_per_hour,
            )
        if indoor_rh >= MOLD_RH_ELEVATED:
            return MoldAssessment(
                "erhöht",
                "Raumluftfeuchte über 70 % – Wanddaten fehlen",
                "Feuchte zeitnah durch Stoßlüften reduzieren",
                None,
                wall_temperature,
                margin,
                max(0.0, duration_high_minutes) / 60,
                trend_rh_per_hour,
            )
        return MoldAssessment(
            "beobachten" if indoor_rh >= 65 else "niedrig",
            "Raumluftfeuchte erhöht – Wanddaten fehlen" if indoor_rh >= 65 else "Feuchte im unkritischen Bereich – Wanddaten fehlen",
            "Raumklima beobachten und Wanddaten wiederherstellen" if indoor_rh >= 65 else "Keine besondere Maßnahme",
            None,
            wall_temperature,
            margin,
            max(0.0, duration_high_minutes) / 60,
            trend_rh_per_hour,
        )

    if wall_temperature is None:
        return MoldAssessment(
            "unbekannt",
            "Wandtemperatur fehlt",
            "Sensorwerte prüfen",
            wall_rh,
            None,
            None,
            max(0.0, duration_high_minutes) / 60,
            trend_rh_per_hour,
        )

    margin = None if dew_point is None else wall_temperature - dew_point
    high_hours = max(0.0, duration_high_minutes) / 60
    elevated_hours = max(0.0, duration_elevated_minutes) / 60

    # Kondensation/Tauwasser ist die kritischste Situation.
    if margin is not None and margin <= 0.5:
        return MoldAssessment(
            "kritisch",
            "Taupunkt wird an der Wand erreicht",
            "Sofort Feuchte abführen und Raum ausreichend warm halten",
            wall_rh,
            wall_temperature,
            margin,
            high_hours,
            trend_rh_per_hour,
        )

    if wall_rh >= MOLD_RH_CRITICAL:
        return MoldAssessment(
            "kritisch",
            "Wandfeuchte über 90 %",
            "Sofort stoßlüften und Ursache der Feuchte prüfen",
            wall_rh,
            wall_temperature,
            margin,
            high_hours,
            trend_rh_per_hour,
        )

    if wall_rh >= MOLD_RH_HIGH:
        action = "Mehrmals täglich kurz stoßlüften"
        reason = "Wandfeuchte über 80 %"
        if high_hours >= 6:
            reason += " seit mindestens 6 Stunden"
            action = "Jetzt gründlich stoßlüften und Feuchte weiter beobachten"
        elif high_hours >= 2:
            reason += " seit mindestens 2 Stunden"
        elif trend_rh_per_hour is not None and trend_rh_per_hour >= MOLD_TREND_WARN_RH_PER_HOUR:
            reason += " und weiter steigend"
            action = "Jetzt lüften, bevor sich die Feuchte weiter erhöht"
        return MoldAssessment(
            "hoch", reason, action, wall_rh, wall_temperature, margin, high_hours, trend_rh_per_hour
        )

    if wall_rh >= MOLD_RH_ELEVATED:
        reason = "Wandfeuchte im erhöhten Bereich"
        if elevated_hours >= 6:
            reason += " über längere Zeit"
        elif trend_rh_per_hour is not None and trend_rh_per_hour >= 2:
            reason += " und steigend"
        return MoldAssessment(
            "erhöht",
            reason,
            "Feuchte zeitnah durch Stoßlüften reduzieren",
            wall_rh,
            wall_temperature,
            margin,
            high_hours,
            trend_rh_per_hour,
        )

    if wall_rh >= MOLD_RH_WATCH or (indoor_rh is not None and indoor_rh >= MOLD_RH_ELEVATED):
        return MoldAssessment(
            "beobachten",
            "Feuchte nähert sich dem Vorsorgebereich",
            "Raumklima beobachten und regelmäßig lüften",
            wall_rh,
            wall_temperature,
            margin,
            high_hours,
            trend_rh_per_hour,
        )

    return MoldAssessment(
        "niedrig",
        "Feuchte im unkritischen Bereich",
        "Keine besondere Maßnahme",
        wall_rh,
        wall_temperature,
        margin,
        high_hours,
        trend_rh_per_hour,
    )
