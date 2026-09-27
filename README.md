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
- Schimmelrisiko an der kältesten Wandstelle (DIN 4108-2), optional CO₂, Wärmeverlust und Kosten pro Lüftung
- Übersicht aller Räume mit Sammel-Benachrichtigung, Anwesenheitserkennung, Ruhezeiten
- Eigene Dashboard-Karte – wird automatisch mitgeliefert, mit Verlaufskurve der letzten Lüftung
- Bad-Modus nach dem Duschen, Warnung bei offenem Fenster wenn alle weg sind, Urlaubsmodus
- Sommer: Kühlen per Lüften inkl. Nachtplan aus der Vorhersage, Luftentfeuchter-Steuerung
- Wochenbericht per Push, Sprachsteuerung („Muss ich lüften?“)

## Sprachsteuerung

Nach der Installation einmal Home Assistant neu starten. Dann versteht Assist u. a.:

- „Muss ich lüften?“
- „Wo soll ich lüften?“
- „Wie ist die Lüftungsempfehlung?“

Die Sätze liegen in `/config/custom_sentences/de/smart_ventilation.yaml` und können dort ergänzt werden (die Datei wird nie überschrieben). Für Automationen gibt es den Dienst `smart_ventilation.status`, der den gleichen Text zurückgibt.

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
| `binary_sensor.wohnzimmer_raum_kuhlt_aus` | Fenster offen und Raum unter der Auskühl-Grenze |
| `binary_sensor.wohnzimmer_ruhezeit` | Ruhezeit aktiv (keine Erinnerungen) |
| `button.wohnzimmer_lernen_zurucksetzen` | Gelernten Luftwechsel verwerfen (Statistik bleibt) |
| `sensor.wohnzimmer_wandtemperatur_geschatzt` | Temperatur an der kältesten Wandstelle |
| `sensor.wohnzimmer_feuchte_an_der_wand` | Relative Feuchte dort – ab 80 % Schimmelgefahr |
| `sensor.wohnzimmer_luftqualitat` | gut / mäßig / schlecht (nur mit CO₂-Sensor) |
| `sensor.wohnzimmer_warmeverlust_luften_heute` | Geschätzter Wärmeverlust durchs Lüften (kWh) |
| `sensor.wohnzimmer_luftungskosten_monat` | Geschätzte Kosten im Monat (€) |
| `sensor.wohnzimmer_kritische_schimmeltage_in_folge` | Tage in Folge mit ≥ 6 h Wandfeuchte über 80 % |
| `binary_sensor.wohnzimmer_schimmelgefahr` | An ab 3 kritischen Tagen in Folge |
| `sensor.wohnzimmer_luftungsbedarf_diesen_monat` | Stunden mit Lüftungsbedarf; Attribut `letzter_monat` mit Vormonats-/Vorjahresvergleich |
| `sensor.luften_ubersicht_dringendster_raum` | Übersicht: Raum mit dem größten Bedarf, Attribut `raeume` |

Eine Lüftung zählt ab 30 Sekunden. **Erfolgreich** ist sie, wenn sie mindestens 2 Minuten dauerte und das Ziel erreicht wurde
(Feuchteunterschied ≤ 0,5 g/m³ **oder** innen ≤ Tagesziel, Standard 11,5 g/m³).

## Installation über HACS

1. HACS öffnen → oben rechts **⋮** → **Benutzerdefinierte Repositories**
2. URL `https://github.com/patrickbrundiers-dev/smart_ventilation` eintragen, Typ **Integration**, hinzufügen
3. **Smart Ventilation** suchen → **Herunterladen**
4. Home Assistant neu starten
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Smart Ventilation**
6. **Raum hinzufügen** wählen und die ersten drei Bereiche ausfüllen (Raum & Fenster, Sensoren im Raum, Außen & Wetter). Die übrigen Bereiche sind zugeklappt und haben sinnvolle Standardwerte.

Für jeden Raum einen eigenen Eintrag anlegen. Optional zusätzlich einmal **Übersicht aller Räume** – dann gibt es eine gemeinsame Nachricht statt einer pro Raum.

Einstellungen später ändern: Gerät öffnen → **Konfigurieren** → Bereich aufklappen → einmal speichern. Gelernte Werte bleiben erhalten.

## Dashboard-Karte

Die Karte wird mit der Integration installiert und automatisch nach `/config/www/smart_ventilation/` kopiert und unter *Einstellungen → Dashboards → Ressourcen* eingetragen (ggf. einmal App/Browser neu laden).

```yaml
type: custom:smart-ventilation-card
device: <Raum oder Übersicht im Editor auswählen>
show_details: true   # Kacheln Innen / Außen / Wand / CO₂
show_chart: true     # Verlauf der letzten Lüftung
```

Ein Tipp auf eine Kachel öffnet den Verlauf des jeweiligen Sensors, ein Tipp auf den Kopf die Empfehlung. Die Karte übernimmt Farben, Rundungen und Schrift deines Themes.

Im Dashboard-Editor unter **Karte hinzufügen → Smart Ventilation** findest du sie auch direkt. Sie zeigt Status, Fortschritt beim Lüften, Innen-/Außen-/Wandwerte, CO₂, besten Zeitpunkt, heutige Statistik und Warnungen. Mit dem Gerät der Übersicht zeigt sie alle Räume.

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

### Version 2.3.6

- **Better Thermostat:** Hat ein Better Thermostat einen eigenen Fenstersensor, schaltet es beim Lüften selbst ab – Smart Ventilation greift dann nicht mehr zusätzlich ein (kein doppeltes Schalten). Ohne Fenstersensor übernimmt Smart Ventilation wie bisher.
- **Klima-Gruppen:** Eine ausgewählte Gruppe wird in ihre Thermostate aufgelöst; ist ein Thermostat zusätzlich einzeln gewählt, wird es trotzdem nur einmal geschaltet.
- Neues Attribut `heizung_selbst_geregelt` am Sensor „Lüftung läuft“.
- Releases werden automatisch angelegt, sobald alle Tests grün sind.

### Version 2.3.5

- **Keine Dauer-Aufforderung mehr:** „Lüften wegen Feuchte“ nur noch, wenn es sich lohnt (draußen mindestens 1 g/m³ trockener) **und** der Raum zu feucht ist (über dem Tagesziel, ab 65 % rel. Feuchte oder bei erhöhtem Schimmelrisiko). Vorher reichten 0,5 g/m³ Unterschied – das Tagesziel wurde dabei nicht beachtet.

### Version 2.3.4

- **Alexa sagt den Raum an:** Alexa Media Player liest nur den Nachrichtentext vor, nicht den Titel. Alexa-Empfänger (`notify.alexa_media_…`) bekommen jetzt einen eigenen, vorlesbaren Text: Raum zuerst, Einheiten ausgeschrieben („Grad“, „Prozent“, „Gramm pro Kubikmeter“), Kommazahlen auf Deutsch. Handys bekommen weiterhin Titel und Aktions-Buttons.

### Version 2.3.3

- Karte lädt auch direkt nach einem Neustart: Sie liegt jetzt unter `/config/www/smart_ventilation/` und wird über `/local/` ausgeliefert – das stellt Home Assistant schon zu Beginn des Starts bereit, das Handy speichert die Datei zwischen. Alte oder doppelte Ressourcen-Einträge werden automatisch bereinigt.

### Version 2.3.2

- Karte wird zusätzlich als **Dashboard-Ressource** eingetragen (wie HACS es für Karten macht) und damit bei jedem Dashboard-Aufruf zuverlässig geladen. Beim Entfernen der Integration wird der Eintrag wieder gelöscht.

### Version 2.3.1

- Karte fehlertolerant: kann nicht mehr „leer hängen bleiben“; bei einem Problem zeigt sie die Fehlermeldung direkt an
- Karte ohne Auswahl zeigt einen Hinweis statt eines Fehlers (Vorschau in der Kartenauswahl funktioniert immer)

### Version 2.3.0

- **Neue Dashboard-Karte**: klare Statusanzeige mit Badge, verständliche Überschrift („Stoßlüften“, „Lüftung läuft“, „Raumklima in Ordnung“), Kacheln mit Füllstandsbalken für Wandfeuchte und CO₂, Hinweis-Banner, Verlauf nur der Feuchte (eine Achse) mit Tooltip beim Antippen, Kacheln öffnen den jeweiligen Sensor. Passt sich schmalen Spalten an, unterstützt Tastatur und „Bewegung reduzieren“.
- **Übersichtskarte** mit Status je Raum, Antippen öffnet den Raum.
- **Einstellungen**: Symbole für jeden Bereich, kurze Beschreibung je Bereich, neuer Bereich „Feinabstimmung“ für selten benötigte Werte; Übersicht in zwei Bereiche gegliedert; Erklärungen im Auswahlmenü.
- **Symbole** aller Entitäten wechseln mit dem Zustand (z. B. Fenster offen/zu, Schild/Warnung beim Schimmelrisiko).

### Version 2.2.0

- **Schimmel-Frühwarnung über mehrere Tage**: Ein Tag gilt als kritisch, wenn die Wand mindestens 6 Stunden über 80 % Feuchte liegt. Ab 3 kritischen Tagen in Folge kommt eine Warnung mit Tipps (nicht in der Ruhezeit, bei anhaltender Lage erneut nach einer Woche). Neue Entitäten „Kritische Schimmeltage in Folge“ und „Schimmelgefahr“, Hinweis in der Karte.
- **Monats- und Jahresvergleich**: Stunden mit Lüftungsbedarf werden erfasst, jeder Monat wird archiviert (3 Jahre). Am 1. des Monats kommt ein **Monatsbericht** mit Vergleich zum Vormonat und – ab dem zweiten Jahr – zum Vorjahr. In der Übersicht mit Rangfolge der Räume.
- **Fix**: Einstellungen ließen sich nicht speichern, wenn ein optionales Feld (z. B. CO₂-Sensor) leer war.

### Version 2.1.1

- **Einstellungen als ein Formular** mit aufklappbaren Bereichen – alles an einer Stelle ändern und einmal speichern
- Neue Reihenfolge: Raum & Fenster → Sensoren im Raum → Außen & Wetter → Lüftungsverhalten → Benachrichtigungen & Abwesenheit → Heizung, Entfeuchter & Kosten
- Zu jedem Feld eine kurze Erklärung, Zahlenfelder mit Einheit
- Entitätsnamen und Zustände (Schimmelrisiko, Luftqualität, Jahreszeit) übersetzt (Deutsch/Englisch)
- Technische Werte (Luftwechsel, Sonnenstand, Taupunkte …) unter „Diagnose“ einsortiert
- Karte: Werte brechen nicht mehr um

### Version 2.1.0

- **Bad-Modus**: Nach dem Duschen (Dusch-Sensor oder erkannt am starken Feuchteanstieg) sofort Lüft-Hinweis – auch in der Ruhezeit. Ist nach 30 Minuten nicht gelüftet und noch feucht, kommt eine Erinnerung.
- **Alle weg, Fenster offen**: Push, sobald die letzte Person das Haus verlässt und noch ein Fenster offen ist.
- **Urlaubsmodus** über Kalender (optional mit Stichwort), Schalter oder Binärsensor: keine Erinnerungen, aber täglich höchstens eine Warnung bei hohem Schimmelrisiko.
- **Sommer: Kühlen per Lüften**: Empfehlung, wenn es drinnen wärmer als die Wohlfühltemperatur (Standard 23 °C) und draußen mind. 2 °C kühler ist. Nachtplan aus der Vorhersage („Heute ab 22:00 bis 07:00 Uhr“). Hinweis zum Schließen, sobald es draußen wärmer wird.
- **Luftentfeuchter**: Wird eingeschaltet, wenn es feucht ist (ab 60 %) und gerade nicht gelüftet werden kann (Regen, Hitze, Ruhezeit, Urlaub, niemand da); aus bei 55 %, offenem Fenster oder wenn kein Bedarf mehr – frühestens nach 15 Minuten.
- **Wochenbericht** sonntags um 19 Uhr – pro Raum oder gesammelt über die Übersicht.
- **Verlaufskurve** der laufenden bzw. letzten Lüftung in der Dashboard-Karte.
- **Sprachsteuerung** über Assist und Dienst `smart_ventilation.status`.

### Version 2.0.0

- **Einrichtung als Assistent** in vier Schritten, Einstellungen als Menü (nur der gewählte Bereich wird geändert)
- **Übersicht aller Räume** (eigener Eintrag): dringendster Raum, Anzahl Räume mit Bedarf, optional **eine Sammel-Nachricht** statt einer pro Raum
- **Anwesenheit**: Personen auswählen – Erinnerungen nur an Anwesende, keine Erinnerung wenn alle weg sind, Hinweis beim Heimkommen
- **Schimmelrisiko an der Wand**: Temperatur an der kältesten Stelle aus Außentemperatur und Dämmstandard (DIN 4108-2, Kriterium 80 %)
- **CO₂-Sensor** (optional): Empfehlung auch bei schlechter Luft, bei sehr schlechter Luft kurz lüften trotz Sommerhitze
- **Wärmeverlust und Kosten** pro Lüftung, Tag und Monat
- **Reparatur-Hinweise**, wenn ein Sensor länger als 10 Minuten ausfällt
- **Eigene Dashboard-Karte** für Räume und Übersicht
- **Automatische Tests** gegen echtes Home Assistant (stabil, Beta und Entwicklungsversion)
- Kompatibel mit Home Assistant 2026.10 (Umstellung von voluptuous auf probatio)

### Version 1.9.0

- **Mehrere Fenster pro Raum**: Lüftung läuft, solange mindestens ein Fenster offen ist. Querlüften (2+ Fenster gleichzeitig) wird erkannt und getrennt gelernt.
- **Auskühl-Warnung**: Push, wenn der Raum bei offenem Fenster unter die Grenze fällt (Standard 18 °C, 0 = aus). Im Winter zusätzlich Hinweis, wenn deutlich länger als nötig gelüftet wird.
- **Ruhezeiten** (Standard 22–7 Uhr) für Lüft-Erinnerungen. Warnungen kommen trotzdem.
- **Buttons in der Push-Nachricht**: „In 30 Min. erinnern“ und „Heute nicht mehr“.
- Nach einer Lüftung 1 Stunde keine neue Erinnerung.
- **Heizung koppeln** (optional): Thermostate nach 1 Min. offenem Fenster aus bzw. auf Minimum, beim Schließen zurück auf den vorherigen Wert.
- **Neustart-fest**: laufende Lüftung, abgesenkte Heizung und „Heute nicht mehr“ überstehen einen Neustart.
- **Button „Lernen zurücksetzen“**
- Fix: „Ziel erreicht“ wurde sofort gemeldet, wenn der Raum schon vor dem Öffnen unter dem Tagesziel lag. Neu zählt auch: 70 % des Feuchteunterschieds abgebaut.

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
