# Smart Ventilation

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/patrickbrundiers-dev/smart_ventilation/actions/workflows/validate.yml/badge.svg)](https://github.com/patrickbrundiers-dev/smart_ventilation/actions/workflows/validate.yml)

Adaptive Lüftungsempfehlung für Home Assistant – pro Raum. Die Integration vergleicht absolute Feuchte innen und außen,
berücksichtigt Wind, Windrichtung zum Fenster, Regen, Temperatur und Sonnenstand und **lernt aus jeder echten Lüftung**,
wie schnell dein Raum tatsächlich Feuchte abgibt.

## Funktionen

**Kern-Empfehlung**
- Adaptive Lüftungsempfehlung pro Raum: vergleicht absolute Feuchte innen/außen, berücksichtigt Wind, Windrichtung zum Fenster, Regen, Temperatur und Sonnenstand
- Lernender Luftwechsel (getrennt nach Wind, Windwinkel und Temperaturdifferenz) – lernt aus jeder echten Lüftung, wie schnell der Raum tatsächlich Feuchte abgibt
- Live-Fortschritt während des Lüftens, Meldung sobald das Ziel erreicht ist
- Empfehlung mit Dauer und Modus (Komplett öffnen / Kippfenster / Querlüften bei mehreren Fenstern)
- Tagesziel absolute Feuchte – mit Raumtyp-Vorschlag beim Einrichten (Schlafzimmer, Bad, Wohnzimmer/Büro, Küche, Sonstige), jederzeit manuell überschreibbar
- Feuchte-Hysterese gegen Flackern der Empfehlung, mit änderbarem Vorgabewert

**Sommer, Winter & Vorheizen**
- Sommer-/Wintermodus manuell oder automatisch: Automatik legt Dezember–Februar/Juni–August fest, entscheidet in den Übergangsmonaten per Außentemperatur – und wechselt erst nach mehreren Stunden anhaltendem Trend, damit sie nicht flackert
- Wärme-Sperre: kein Lüften, wenn es draußen deutlich wärmer ist als drinnen (ganzjährig)
- Sommer: Kühlen per Lüften (Komforttemperatur einstellbar) inkl. Kühl-Zeitfenster aus der Wettervorhersage
- Vorheizen: nach einer Nacht unter der Heizgrenze darf tagsüber trotz wärmerer Außenluft gelüftet werden, um Heizkosten zu sparen – inkl. Regen-Vorschau und Vorschau, ab wann es warm genug wird

**Gesundheit & Luftqualität**
- Relative Feuchte, Taupunkt und Schimmelrisiko-Einschätzung an der kältesten Wandstelle (DIN 4108-2, mehrere Dämmstandards wählbar)
- Schimmel-Frühwarnung bei mehreren kritischen Tagen in Folge
- Optional CO₂-Sensor: Luftqualität gut/mäßig/schlecht, eigene CO₂-Lüftungsempfehlung

**Automatisierung & Komfort**
- Bester Lüftungszeitpunkt aus der stündlichen Wettervorhersage (nächste 24 h)
- Gekoppelte Heizung wird bei offenem Fenster automatisch abgesenkt und danach wiederhergestellt
- Auskühl-Warnung, wenn der Raum bei offenem Fenster zu kalt wird
- Bad-Modus nach dem Duschen (Sensor oder automatische Erkennung über Feuchtesprung) mit Nachfass-Erinnerung
- Urlaubsmodus: normale Erinnerungen aus, Schimmelrisiko bleibt überwacht
- Luftentfeuchter-Steuerung nach relativer Feuchte
- Warnung bei offenem Fenster, wenn niemand zu Hause ist

**Statistik & Kosten**
- Lüftungsstatistik heute/Woche/Monat/gesamt, ganz ohne eigene Helfer oder Automationen
- Geschätzter Wärmeverlust (kWh) und Kosten (€) je Lüftung und Monat
- Monats-/Jahresvergleich des Lüftungsbedarfs mit Vormonats-/Vorjahreswerten
- Wochenbericht per Push

**Bedienung**
- Push-Benachrichtigungen mit Cooldown, Ruhezeiten und Snooze-/Überspringen-Aktionen direkt in der Nachricht
- Übersicht aller Räume mit Sammel-Benachrichtigung statt einer pro Raum
- Eigene Dashboard-Karte (wird automatisch mitinstalliert) mit Verlaufskurve, Status-Kacheln und Fortschrittsanzeige
- Sprachsteuerung über Assist („Muss ich lüften?“, „Wo soll ich lüften?“) sowie ein Dienst für eigene Automationen
- Reparatur-Hinweise bei ausgefallenen Sensoren
- Alle Einstellungen nachträglich änderbar, ohne Lerndaten zu verlieren
- Deutsch und Englisch

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

### Version 2.3.26

- **Feuchte-Schutz beim Vorheizen**: Ist die Luft draußen deutlich feuchter als drinnen, wird nicht mehr vorgeheizt, auch wenn Temperatur und Nacht-Tiefstwert dafür sprächen – sonst würde man sich mit der Wärme zugleich ein Feuchteproblem einhandeln (spiegelbildlich zum bestehenden Feuchte-Schutz beim Sommer-Kühlen).
- **Windrichtung fließt jetzt auch in die Vorhersage ein**: Liefert die Wetter-Integration eine Windrichtung pro Stunde, werden der beste Lüftungszeitpunkt sowie die Kühlen-/Vorheizen-Vorschau bevorzugt für Stunden mit günstigem Wind (zum Fenster hin statt vom Fenster weg) berechnet. Ohne Richtungsangabe in der Vorhersage ändert sich nichts.
- **Kühlen und Vorheizen nutzen jetzt das gebuckete Luftwechsel-Modell** (nach Wind, Windwinkel und Temperaturdifferenz gelernt) statt nur des groben globalen Durchschnitts – wie es die normale Lüftungsdauer-Schätzung schon immer tut. Das macht die geschätzte Dauer für die aktuellen Bedingungen genauer, sobald dafür genug gelernt wurde.
- **Vorheizen zeigt jetzt eine Ersparnis in der Statistik**: Lüftungen, die als Vorheizen erkannt wurden, tauchen nicht mehr nur als Wärmeverlust, sondern zusätzlich als eingesparte Heizenergie (kWh/€) auf – heute/Woche/Monat/gesamt, im Wochenbericht und in einem neuen Sensor „Vorheiz-Ersparnis Monat“.

### Version 2.3.25

- **Automatik-Modus nutzt jetzt zusätzlich die mehrtägige Wettervorhersage** (nur wenn eine Wetter-Entität gewählt ist): Zeigt die Vorhersage für die nächsten Tage durchgehend eindeutig Hoch UND Tief auf einer Seite der Heizgrenze, wird der Sommer-/Wintermodus sofort übernommen – ohne erst mehrere Stunden auf die lokale Außentemperatur zu warten (SEASON_CONFIRM_HOURS aus 2.3.19). Ein mehrtägiger Vorhersage-Trend ist ein verlässlicheres, längerfristigeres Signal als ein paar Stunden lokale Messwerte. Ohne Wetter-Entität oder bei uneindeutiger Vorhersage bleibt es beim bisherigen Verhalten.

### Version 2.3.24

- Korrektur zu 2.3.23: Der Versuch, die kurze GitHub-Repo-Beschreibung automatisch bei jedem Release zu aktualisieren, hat die Release-Pipeline lahmgelegt (der Standard-Workflow-Token kann keine Repo-Einstellungen ändern, egal welche Berechtigung man ihm gibt). Zurückgenommen – kein Verhaltensunterschied in der Integration selbst.

### Version 2.3.23

- ~~GitHub-Repo-Beschreibung wird jetzt automatisch mit aktualisiert~~ (siehe 2.3.24 – ließ sich mit dem Standard-Workflow-Token nicht umsetzen).

### Version 2.3.22

- **Feldbeschreibungen in den Einstellungen aktualisiert:** Die Beschreibungen zu „Sommer-/Wintermodus“ und „Vorheizen ab“ erklären jetzt direkt in der App, dass die Automatik erst nach mehreren Stunden Trend umschaltet und dass Vorheizen nur bei manuell eingestelltem Sommer-Modus blockiert wird (nicht bei „Automatisch“). Kein Verhaltensunterschied, nur Doku.

### Version 2.3.21

- **Präzisierung zu 2.3.20:** Vorheizen soll gezielt nur in der Heizsaison passieren, nicht unnötig Wärme in den echten Sommer holen. Deshalb wird jetzt wieder ein Sommer-Modus berücksichtigt – aber nur, wenn er **manuell** eingestellt ist. Steht ein Raum auf „Automatisch“, zählt weiterhin nur die tatsächliche Nacht-Tiefsttemperatur, weil die automatische Sommer/Winter-Erkennung (seit 2.3.19 bewusst träge) in der Übergangszeit tagelang „Sommer“ zeigen kann, obwohl es nachts schon unter die Heizgrenze fällt – genau dann soll Vorheizen ja Heizkosten sparen.

### Version 2.3.20

- **Fix: Vorheizen funktionierte nicht mehr, solange der Modus noch „Sommer“ zeigte.** Seit 2.3.19 reagiert die Sommer/Winter-Automatik erst nach mehreren Stunden anhaltendem Trend, damit sie nicht mehr flackert. Gerade in der Übergangszeit (Herbst/Frühling) gibt es aber schon einzelne kalte Nächte, obwohl der Modus wegen warmer Tage noch auf „Sommer“ steht – Vorheizen wäre dadurch blockiert gewesen, obwohl die eigentliche Voraussetzung (kalte Nacht) erfüllt war. Vorheizen prüft jetzt nur noch die Nacht-Tiefsttemperatur direkt und ist unabhängig von der Sommer/Winter-Einstufung.

### Version 2.3.19

- **Fix: Automatik-Modus konnte an einem Tag mehrfach zwischen Sommer und Winter hin- und herspringen.** In den Übergangsmonaten (März–Mai, September–November) entschied bisher die aktuelle Außentemperatur sofort – bei Tagen mit großer Spanne (kalte Nacht, warmer Nachmittag) konnte das den Modus (und damit z. B. Vorheizen/Kühlen) mehrmals täglich umschalten, obwohl sich an der Jahreszeit nichts geändert hatte. Die Außentemperatur muss jetzt mindestens 6 Stunden ununterbrochen deutlich über bzw. unter der Heizgrenze liegen, bevor der Modus tatsächlich wechselt.

### Version 2.3.18

- **Vorheizen berücksichtigt jetzt die Wettervorhersage** (nur wenn eine Wetter-Entität eingerichtet ist):
  - **Regen-Vorschau:** Droht laut Vorhersage in den nächsten ca. 2 Stunden Regen, wird nicht mehr zum Vorheizen geöffnet – auch wenn es gerade noch trocken ist.
  - **Vorschau auf den nächsten Zeitpunkt:** Ist es aktuell noch nicht warm genug, zeigt die Karte an, ab wann es laut Vorhersage voraussichtlich warm (und trocken) genug wird, um vorzuheizen.

### Version 2.3.17

- **Neu: Vorheizen per Lüften (Winter).** Ist ein Raum unter der neuen Schwelle „Winter: vorheizen ab“ (Vorgabe 19 °C) und es war die letzte Nacht (22–9 Uhr) schon einmal kälter als die eingestellte Heizgrenze (Vorgabe 15 °C), darf tagsüber trotz wärmerer Außenluft gelüftet werden, um warme Luft statt Heizungswärme in den Raum zu holen und so das Heizen hinauszuzögern bzw. den Raum warm zu halten. Voraussetzung ist außerdem, dass es draußen mindestens 2 °C wärmer ist als drinnen – sonst bringt das Lüften keinen Vorteil.
  - **Kein Widerspruch zur Wärme-Sperre aus 2.3.14:** Die „draußen zu warm“-Sperre bleibt für alle anderen Gründe (Feuchte, CO₂) unverändert bestehen. Nur wenn tatsächlich zum Vorheizen gelüftet werden soll, gilt sie ausnahmsweise nicht – dort ist die wärmere Außenluft ja gerade der Grund fürs Lüften, nicht ein Störfaktor. Ebenso erscheint dabei nicht der Hinweis „Fenster schließen“, der sonst bei wärmer werdender Außenluft kommt.
  - Die Vorheiz-Schwelle ist ein eigener, unabhängiger Wert (nicht die Sommer-Wohlfühltemperatur) und lässt sich unter „Lüftungsverhalten“ einstellen.

### Version 2.3.16

- **Feuchte-Hysterese jetzt pro Raum einstellbar:** Der Puffer gegen das Flackern der Feuchte-Empfehlung an der Schwelle (seit 2.3.12 fest im Code) lässt sich jetzt unter „Lüftungsverhalten“ als „Feuchte-Puffer gegen Flackern“ anpassen. Vorgabewert bleibt 0,1 g/m³, höher = ruhiger/träger, niedriger = reagiert schneller.

### Version 2.3.15

- **Fix: Statistik nach Neustart konnte verfälscht sein.** Schloss sich ein Fenster während HA nicht lief (Neustart, Update) und kamen zwischen dem tatsächlichen Schließen und dem Wiederhochfahren mehrere Stunden zusammen, wurde beim Nachtragen der Lüftung fälschlich mit den dann aktuellen (aber längst nicht mehr aussagekräftigen) Sensorwerten geprüft, ob das Ziel erreicht wurde – eine zufällig trockene Raumluft Stunden später konnte so eine eigentlich wirkungslose Lüftung als „erfolgreich“ in die Statistik eintragen. Zählt jetzt nur noch, was schon vor dem Neustart als erreicht festgehalten war.
- Kleinere Doku-Korrektur bei der internen Benachrichtigungs-Filterung (kein Verhaltensunterschied).

### Version 2.3.14

- **Fix: Im Winter wurde trotz wärmerer Außenluft weiter „Lüften“ empfohlen.** Die Wärme-Sperre („draußen zu warm“) galt bisher nur im Sommer – im Winter wurde sie komplett übersprungen, auch an milden Tagen, an denen es draußen tatsächlich wärmer war als drinnen. Jetzt gilt dieselbe Grenze (Standard 3 °C) unabhängig von der Jahreszeit; ebenso der Hinweis zum Fenster schließen, falls es während des Lüftens wärmer wird.
- **Automatik-Modus berücksichtigt jetzt den Kalendermonat:** Dezember–Februar gelten fest als Winter, Juni–August fest als Sommer – ein einzelner milder Wintertag oder kühler Sommertag schaltet den Modus nicht mehr um. Nur in den Übergangsmonaten (März–Mai, September–November) entscheidet weiter die Außentemperatur wie bisher.

### Version 2.3.13

- **Richtwert für das Tagesziel je Raumtyp:** Beim Einrichten eines Raums lässt sich jetzt ein Raumtyp wählen (Schlafzimmer, Bad, Wohnzimmer/Büro, Küche, Sonstige). Danach wird das Tagesziel Luftfeuchte automatisch auf einen dazu passenden Richtwert vorbelegt (z. B. Schlafzimmer niedriger wegen Schimmelrisiko an Außenwänden, Bad höher wegen kurzfristiger Spitzen durchs Duschen) – lässt sich aber jederzeit manuell überschreiben, dann bleibt der eigene Wert erhalten.

### Version 2.3.12

- **Feuchte-Empfehlung flackert nicht mehr:** Die Empfehlung „wegen Feuchte lüften“ konnte direkt an der Schwelle bei jeder kleinen Sensorschwankung an- und ausgehen (sichtbar als ständiger Wechsel zwischen „Kippfenster …“ und „Keine Lüftung erforderlich“ im Verlauf, teils im Minutentakt). Jetzt gilt eine Hysterese: Ist die Empfehlung erst aktiv, braucht es einen spürbar deutlicheren Rückgang (Feuchteunterschied, Zielwert, rel. Feuchte und Schimmelrisiko gemeinsam klar unter der Schwelle), bevor sie wieder ausgeht.

### Version 2.3.11

- **Pause nach dem Lüften nutzt die Wettervorhersage:** Statt starr 60 Minuten zu warten, gilt bei eingerichteter Wetter-Entität der nächste günstige Zeitpunkt aus der Vorhersage – aber höchstens 4 Stunden voraus, sonst bleibt es bei 60 Minuten. So kommt keine Erinnerung, während draußen gerade Regen oder Hitze herrscht, aber auch keine unnötig lange Pause.
- **Ausnahme bei Extremwerten:** Ist das Schimmelrisiko hoch oder der CO₂-Wert hoch, gilt die Pause gar nicht – dann wird trotzdem sofort wieder zum Lüften geraten.

### Version 2.3.10

- Kleiner Timing-Fix: Attribute (u. a. der neue Heizungsstatus) werden jetzt immer am Ende jeder Prüfrunde aktualisiert, nicht nur am Anfang – vorher konnte die Karte bis zu 30 Sekunden hinterherhinken.
- **Heizung sichtbar auf der Karte:** Solange gelüftet wird, zeigt die Karte jetzt, welche Heizung abgesenkt wird und wann sie wiederhergestellt wird. Regelt Better Thermostat oder der Climate Group Helper das Fenster selbst, steht das dort ebenfalls.

### Version 2.3.9

- **„Pausiert“ auf der Karte:** Gelten gerade dieselben Sperren wie für Benachrichtigungen (Pause nach dem Lüften, Ruhezeit, „In 30 Min. erinnern“, „Heute nicht mehr“, Urlaub, niemand zu Hause), zeigt die Karte „Pausiert“ mit Grund statt „Lüften“. Die Empfehlung bleibt klein darunter sichtbar; die Übersicht zählt pausierte Räume nicht mehr mit.
- Karte lädt robuster: Frontend-Modul und Dashboard-Ressource nutzen getrennte Adressen – schlägt ein Weg fehl (z. B. beim Laden während eines Neustarts), lädt der andere trotzdem.

### Version 2.3.8

- **Better Thermostat + Climate Group Helper:** Die Heizungs-Hierarchie wird erkannt (Thermostate → Climate Group Helper → Better Thermostat). Geschaltet wird immer die oberste Ebene – egal ob im Raum das BT, die Gruppe oder ein einzelnes Thermostat gewählt ist. So regelt Better Thermostat nicht dagegen.
- Hat Better Thermostat einen Fenstersensor **oder** der Climate Group Helper eine Fenstersteuerung, überlässt Smart Ventilation das Abschalten diesen Integrationen.

### Version 2.3.7

- **Kein Widerspruch mehr zwischen „Lüften“ und „Fenster schließen“:** Die Warnung „draußen zu warm“ nutzt jetzt dieselbe Sommer-Grenze wie die Empfehlung. Nur wenn zum **Kühlen** gelüftet wird, kommt sie schon, sobald es draußen wärmer als drinnen ist.

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
