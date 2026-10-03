"""HA-independent Schimmelrisiko-Bewertung.

Die Schwellenwerte orientieren sich an den UBA-Hinweisen:
- Raumluft dauerhaft <= 65–70 % RH
- Material-/Wandoberfläche < 80 % RH
- Kondensation ist besonders kritisch

Die Berechnung ist eine konservative Frühwarnung, keine Bauwerksdiagnose.
"""
from __future__ import annotations

from dataclasses import dataclass


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


def assess_mold_risk(
    wall_rh: float | None,
    wall_temperature: float | None,
    indoor_rh: float | None,
    dew_point: float | None,
    duration_high_minutes: float = 0.0,
    duration_elevated_minutes: float = 0.0,
    trend_rh_per_hour: float | None = None,
) -> MoldAssessment:
    if wall_rh is None or wall_temperature is None:
        return MoldAssessment(
            "unbekannt",
            "Wanddaten fehlen",
            "Sensorwerte prüfen",
            wall_rh,
            wall_temperature,
            None if dew_point is None or wall_temperature is None else wall_temperature - dew_point,
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

    if wall_rh >= 90:
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

    if wall_rh >= 80:
        action = "Mehrmals täglich kurz stoßlüften"
        reason = "Wandfeuchte über 80 %"
        if high_hours >= 6:
            reason += " seit mindestens 6 Stunden"
            action = "Jetzt gründlich stoßlüften und Feuchte weiter beobachten"
        elif high_hours >= 2:
            reason += " seit mindestens 2 Stunden"
        elif trend_rh_per_hour is not None and trend_rh_per_hour >= 2:
            reason += " und weiter steigend"
            action = "Jetzt lüften, bevor sich die Feuchte weiter erhöht"
        return MoldAssessment(
            "hoch", reason, action, wall_rh, wall_temperature, margin, high_hours, trend_rh_per_hour
        )

    if wall_rh >= 70:
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

    if wall_rh >= 65 or (indoor_rh is not None and indoor_rh >= 70):
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
