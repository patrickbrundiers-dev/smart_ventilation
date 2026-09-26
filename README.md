# Smart Ventilation

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/patrickbrundiers-dev/smart_ventilation/actions/workflows/validate.yml/badge.svg)](https://github.com/patrickbrundiers-dev/smart_ventilation/actions/workflows/validate.yml)

Adaptive Lüftungsempfehlung für Home Assistant – pro Raum. Die Integration vergleicht absolute Feuchte innen und außen,
berücksichtigt Wind, Windrichtung zum Fenster, Regen, Temperatur und Sonnenstand und **lernt aus jeder echten Lüftung**,
wie schnell dein Raum tatsächlich Feuchte abgibt.

## Funktionen

- Empfehlung mit Dauer und Modus (Komplett öffnen / Kippfenster)
- Lernender Luftwechsel, getrennt nach Wind, Windwinkel und Temperaturdifferenz
- Live-Fortschritt während des Lüftens und Meldung, sobald das Ziel erreicht ist
- Relative Feuchte, Taupunkt und einfache Schimmelrisiko-Einschätzung
- Optionale Push-Benachrichtigungen mit Cooldown
- Alle Einstellungen nachträglich änderbar, ohne Lerndaten zu verlieren
- Lüftungsstatistik (heute / Woche / Monat / gesamt) und Tagesziel – ohne eigene Helfer oder Automationen

## Entitäten (Beispiel Raum „Wohnzimmer“)

| Entität | Bedeutung |
|---|---|
| `binary_sensor.wohnzimmer_luften_empfohlen` | Jetzt lüften? Attribute: `modus`, `dauer_min` |
| `binary_sensor.wohnzimmer_heute_geluftet` | Tagesziel erreicht |
| `sensor.wohnzimmer_luftungen_heute` / `_woche` / `_monat` / `_gesamt` | Anzahl; Attribute `erfolgreich`, `ohne_ziel`, `dauer_gesamt_min`, `dauer_durchschnitt_min` |
| `sensor.wohnzimmer_aktuelle_luftungsdauer` | Sekunden seit Öffnen |
| `sensor.wohnzimmer_langste_luftung` | Rekord in Minuten |
| `sensor.wohnzimmer_empfehlung` | Klartext-Empfehlung |
| `sensor.wohnzimmer_bester_luftungszeitpunkt` | Zeitstempel der besten Stunde (nächste 24 h); Attribut `text` z. B. „Heute 14:00 Uhr“ |
| `sensor.wohnzimmer_jahreszeit_modus` | Sommer / Winter |

Eine Lüftung zählt ab 30 Sekunden. **Erfolgreich** ist sie, wenn sie mindestens 2 Minuten dauerte und das Ziel erreicht wurde
(Feuchteunterschied ≤ 0,5 g/m³ **oder** innen ≤ Tagesziel, Standard 11,5 g/m³).

## Installation über HACS

1. HACS öffnen → oben rechts **⋮** → **Benutzerdefinierte Repositories**
2. URL `https://github.com/patrickbrundiers-dev/smart_ventilation` eintragen, Typ **Integration**, hinzufügen
3. **Smart Ventilation** suchen → **Herunterladen**
4. Home Assistant neu starten
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Smart Ventilation**

Für jeden Raum einen eigenen Eintrag anlegen.

### Manuelle Installation

Ordner `custom_components/smart_ventilation` nach `/config/custom_components/` kopieren und neu starten.

## Voraussetzungen

Pro Raum:
- Sensor absolute Feuchte innen und außen (g/m³)
- Temperatur innen und außen
- Windgeschwindigkeit (km/h oder m/s) und Windrichtung (°)
- Regensensor (Binärsensor oder mm/h)
- Fensterkontakt

Home Assistant **2024.11** oder neuer.

## Tipps

- **Sommer/Winter-Modus** auf „Automatisch“ lassen – im Winter wird dann kurz stoßgelüftet statt blockiert.
- **Sommer-Grenze** (Standard 3 °C): Ist es draußen um mehr als diesen Wert wärmer, wird nicht gelüftet.
- **Fensterausrichtung**: Richtung, in die das Fenster zeigt (0 = Nord, 90 = Ost, 180 = Süd, 270 = West).

> Die Schimmelrisiko-Einschätzung basiert nur auf der Raumluft und ersetzt keine bauphysikalische Bewertung von Wandoberflächen.

## Changelog

### Version 1.8.0

- **Bester Lüftungszeitpunkt** aus der stündlichen Wettervorhersage (optional, Wetter-Entität in den Einstellungen wählen)
  - bewertet die nächsten 24 h zwischen 7 und 22 Uhr
  - rechnet die absolute Außenfeuchte aus Taupunkt oder Temperatur + Luftfeuchte
  - schließt Regenstunden und im Sommer zu heiße Stunden aus, bevorzugt im Winter mildere Stunden, Wind gibt einen Bonus
  - aktualisiert sich alle 30 Minuten
- Voraussetzung: Der Wetterdienst muss eine **stündliche** Vorhersage mit Luftfeuchte oder Taupunkt liefern (z. B. Met.no, OpenWeatherMap, DWD)

### Version 1.7.0

- **Sommer/Winter-Modus** (Automatisch, Sommer, Winter)
  - Winter: keine Temperatursperre mehr, stattdessen Stoßlüften mit Höchstdauer je nach Außentemperatur (unter 5 °C: 5 Min., unter 10 °C: 10 Min., sonst 15 Min.), nie Kippfenster
  - Sommer: nicht lüften, wenn es draußen deutlich wärmer ist als drinnen (Standard 3 °C)
  - Automatik schaltet nach Außentemperatur um (Standard 15 °C, mit 1 °C Hysterese)
  - Neuer Sensor „Jahreszeit-Modus“
- **Empfänger per Auswahlliste**: alle Handys mit Home-Assistant-App ankreuzen, mehrere möglich. Ein offline Handy blockiert die anderen nicht.
- Bestehende Einträge übernehmen den bisher eingetragenen notify-Dienst automatisch

### Version 1.6.1

- Fix: Integration startete nicht (`async_track_time_interval` mit vertauschten Argumenten, Fehler aus dem Original-Code)

### Version 1.6.0

- Statistik-Sensoren für heute, Woche, Monat, gesamt, aktuelle und längste Lüftung
- Binärsensoren „Heute gelüftet“ und „Lüften empfohlen“ (für Automationen)
- Tagesziel (absolute Feuchte innen) einstellbar
- Fix: Attribut-Änderungen am Fensterkontakt (z. B. Batterie) starten die Lüftung nicht mehr neu
- Jede Öffnung wird gezählt, auch wenn innen nicht feuchter war als außen
- Zeitberechnung nutzt die Home-Assistant-Zeitzone

### Version 1.5.0

- Optionen-Seite: Einstellungen jederzeit ändern über Geräte & Dienste -> Smart Ventilation -> Konfigurieren. Gelernte Werte bleiben erhalten.
- Deutsche (und englische) Feldbezeichnungen im Einrichtungsdialog
- Ein Raum kann nicht mehr versehentlich doppelt angelegt werden

### Version 1.4.1 (Bugfix)

- Syntaxfehler in `sensor.py` behoben (Integration lud nicht)
- `manifest.json`: `config_flow: true` – Integration erscheint jetzt unter „Integration hinzufügen“
- Lernformel korrigiert: Luftwechsel wurde um Faktor 60 zu niedrig berechnet
- Notify-Dienst und Cooldown (Minuten) sind jetzt im Einrichtungsdialog einstellbar
- Keine Erinnerung, während das Fenster schon offen ist; Cooldown gilt global
- Regen: numerische Sensoren (mm/h > 0) werden erkannt
- Lüften bis unter Außenniveau wird nicht mehr verworfen
- Sensoren aktualisieren sich per Push, haben Geräteklassen (Statistik/Verlauf) und Raumnamen als Präfix

### Version 1.4

### Feedback-Regelkreis

Während ein Fenster geöffnet ist, prüft die Integration alle 30 Sekunden den tatsächlichen Fortschritt.

Beispiel:

1. `Jetzt wäre ein guter Zeitpunkt zum Lüften – ca. 6 Minuten.`
2. Fenster wird geöffnet.
3. `Lüftung läuft` wird aktiv.
4. Feuchteabbau wird laufend verfolgt.
5. Sobald der Zielwert erreicht ist:
   `Das Lüftungsziel ist erreicht – Feuchteunterschied nur noch 0,4 g/m³.`
6. Beim Schließen:
   `Lüftung abgeschlossen – 7,1 Minuten, Feuchteunterschied 4,7 → 0,4 g/m³.`
7. Der reale Vorgang fließt anschließend in das Lernmodell ein.

Neue Sensoren:
- `Lüftung läuft`
- `Lüftungsfortschritt`

Damit entsteht ein geschlossener Feedback-Regelkreis aus Empfehlung -> tatsächlichem Lüften -> Ergebnis -> Lernen.

### Version 1.3

### Intelligente Benachrichtigungen
Optional kann ein Home-Assistant-Notify-Dienst hinterlegt werden.

Beispiel:
`notify.mobile_app_patrick`

Wenn die Bedingungen zum Lüften erfüllt sind, wird eine Nachricht erzeugt:

> Jetzt wäre ein guter Zeitpunkt zum Lüften – Komplett öffnen, voraussichtlich 6 Minuten.

Die Benachrichtigung besitzt einen Cooldown, damit bei häufigen Sensoränderungen keine Meldungsschleife entsteht.

### Version 1.2

### Kontextabhängiges Lernen
Das System lernt nicht mehr nur einen einzigen Luftwechselwert. Es legt Modelle nach folgenden Bedingungen an:

- Windgeschwindigkeit
- Windrichtung relativ zum Fenster
- Temperaturdifferenz innen/außen

Nach mindestens zwei passenden Lernvorgängen wird das passende Kontextmodell bevorzugt. Zusätzlich bleibt ein allgemeines Modell als Fallback.

### Taupunkt und Raumfeuchte
Aus absoluter Feuchte und Temperatur werden näherungsweise berechnet:

- relative Luftfeuchte innen/außen
- Taupunkt innen/außen

### Schimmelrisiko
Es gibt eine einfache Luftfeuchte-/Taupunkt-Warnung:

- niedrig
- erhöht
- hoch

Das ist ausdrücklich keine Aussage über die tatsächliche Oberflächentemperatur einer Wand und ersetzt keine bauphysikalische Bewertung.

### Sonnenstand
- Sonnenhöhe
- Sonnenazimut
- Fenster-Ausrichtung
- direkte Sonneneinstrahlung

Bei direkter Sonne wird die Lüftungsdauer begrenzt.

### Persistenz
Das gelernte Modell wird ohne Home-Assistant-Helper dauerhaft im Storage der Integration gespeichert. Die erzeugten Sensoren werden zusätzlich ganz normal vom Home-Assistant-Recorder aufgezeichnet.
