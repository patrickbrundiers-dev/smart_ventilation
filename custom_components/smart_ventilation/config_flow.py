"""Einrichtung und Einstellungen als ein Formular mit aufklappbaren Bereichen."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

# HA ≤ 2026.9 nutzt voluptuous, ab 2026.10 probatio (gleiche API) – dieselbe Bibliothek wie HA verwenden
vol = getattr(cv, "probatio", None) or cv.vol

from .const import (
    DOMAIN, CONF_NAME, CONF_VOLUME, CONF_WINDOW_DIRECTION,
    CONF_INDOOR_HUMIDITY, CONF_OUTDOOR_HUMIDITY, CONF_INDOOR_RH, CONF_OUTDOOR_RH,
    CONF_INDOOR_TEMP, CONF_OUTDOOR_TEMP,
    CONF_SOLAR_RADIATION, CONF_THUNDERSTORM, CONF_WIND_GUST, CONF_FROST,
    CONF_WIND_SPEED, CONF_WIND_DIRECTION, CONF_WIND_IS_FROM, CONF_RAIN, CONF_WINDOW,
    CONF_MAX_TEMP_DIFF, CONF_USE_SUN, CONF_MIN_SUN_ELEVATION, CONF_SUN_ENTITY,
    DEFAULT_MAX_TEMP_DIFF, DEFAULT_MIN_SUN_ELEVATION, DEFAULT_SUN_ENTITY,
    DEFAULT_NOTIFICATION_COOLDOWN, CONF_NOTIFY_SERVICE, CONF_NOTIFY_SERVICES,
    CONF_NOTIFICATION_COOLDOWN, CONF_TARGET_ABS, DEFAULT_TARGET_ABS,
    CONF_ROOM_TYPE, DEFAULT_ROOM_TYPE, ROOM_TYPE_TARGET_ABS,
    CONF_HUMID_HYSTERESIS, DEFAULT_HUMID_HYSTERESIS,
    CONF_SEASON_MODE, CONF_SEASON_THRESHOLD, DEFAULT_SEASON_MODE, DEFAULT_SEASON_THRESHOLD,
    SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER, CONF_WEATHER, CONF_COOL_LIMIT,
    DEFAULT_COOL_LIMIT, CONF_QUIET_START, CONF_QUIET_END, DEFAULT_QUIET_START,
    DEFAULT_QUIET_END, CONF_CLIMATES, CONF_CO2, CONF_BUILDING, DEFAULT_BUILDING, U_VALUES,
    CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE, CONF_PERSONS, CONF_ENTRY_TYPE,
    ENTRY_TYPE_ROOM, ENTRY_TYPE_OVERVIEW, CONF_COMBINE, CONF_SHOWER, CONF_SHOWER_DETECT,
    CONF_VACATION, CONF_VACATION_KEYWORD, CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP,
    CONF_PREHEAT_TEMP, DEFAULT_PREHEAT_TEMP,
    CONF_DEHUMIDIFIER, CONF_SHUTTER, CONF_WEEKLY_REPORT, CONF_MONTHLY_REPORT,
    CONF_QUIET_WEEKEND_DIFFERENT, CONF_QUIET_START_WEEKEND, CONF_QUIET_END_WEEKEND,
    CATEGORY_CONF_KEYS, CAT_REMINDER, CAT_REPORT,
)

# Reihenfolge der Bereiche im Formular
# "Feinabstimmung" wurde aufgelöst: Windrichtung/Sonne stecken jetzt bei "outdoor" (deren Sensoren),
# Winterschwelle bei "behavior" (neben dem Sommer-/Wintermodus) und der Erinnerungsabstand bei "notify" –
# so findet man ein Feld dort, wo man wegen des zugehörigen Themas ohnehin schon hinschaut.
SECTIONS = ["room", "indoor", "outdoor", "behavior", "notify", "devices"]
OVERVIEW_SECTIONS = ["messages", "reports"]
# Bei der Ersteinrichtung offen (enthalten Pflichtfelder), der Rest zugeklappt
OPEN_ON_SETUP = {"room", "indoor", "outdoor"}

# Optionale Felder: werden leer gespeichert, wenn der Nutzer sie entfernt
OPTIONAL_EMPTY = {
    CONF_CO2: "", CONF_SHOWER: "", CONF_WEATHER: "", CONF_VACATION: "",
    CONF_VACATION_KEYWORD: "", CONF_NOTIFY_SERVICES: [], CONF_PERSONS: [],
    CONF_CLIMATES: [], CONF_DEHUMIDIFIER: "", CONF_INDOOR_RH: "", CONF_OUTDOOR_RH: "",
    CONF_SHUTTER: "", CONF_SOLAR_RADIATION: "", CONF_THUNDERSTORM: "", CONF_WIND_GUST: "",
    CONF_FROST: "",
}


# ----------------------------------------------------------------------
# Bausteine
# ----------------------------------------------------------------------
def _entity(domain, multiple=False):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain, multiple=multiple))


def _number(minimum, maximum, step, unit=None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _select(options, key):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, translation_key=key, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def _req(key, value):
    """Pflichtfeld – nur vorbelegen, wenn es einen Wert gibt."""
    return vol.Required(key, default=value) if value not in (None, "", []) else vol.Required(key)


def _opt(key, value):
    """Optionales Feld – Vorschlag statt Default, damit es sich leeren lässt.

    Leere Werte ("" oder []) NICHT vorschlagen: das Frontend würde sie sonst mitschicken,
    und HA lehnt z. B. eine leere Entität beim Speichern ab.
    """
    if value in (None, "", []):
        return vol.Optional(key)
    return vol.Optional(key, description={"suggested_value": value})


def _notify_label(service: str) -> str:
    name = service.removeprefix("notify.")
    if name.startswith("mobile_app_"):
        return name.removeprefix("mobile_app_").replace("_", " ").title() + " (App)"
    return name.replace("_", " ").title()


def _notify_selector(hass: HomeAssistant, current: list[str]):
    services = [
        f"notify.{name}"
        for name in hass.services.async_services_for_domain("notify")
        if name not in ("notify", "persistent_notification", "send_message")
    ]
    services = sorted(set(services) | set(current), key=lambda s: (not s.startswith("notify.mobile_app_"), s))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=s, label=_notify_label(s)) for s in services],
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _category_fields(d: dict, current: list[str], categories=None) -> dict:
    """Je Benachrichtigungsart eigene Empfänger wählbar – nur sinnvoll ab zwei Zielen.

    Auswahl-Optionen sind absichtlich nur die bereits unter „Benachrichtigen über“ gewählten
    Ziele (nicht alle System-Dienste): hier wird nur eingeschränkt, wer von den gewählten
    Zielen welche Art Nachricht bekommt. Ohne bewusste Auswahl bleiben alle Ziele aktiv.

    `categories` schränkt ein, welche der 7 Arten angeboten werden – die Übersicht verschickt
    z. B. nur Erinnerungen und Berichte, keine Dusch- oder Schimmelwarnungen.
    """
    if len(current) < 2:
        return {}
    options = [selector.SelectOptionDict(value=s, label=_notify_label(s)) for s in current]
    keys = CATEGORY_CONF_KEYS if categories is None else {c: CATEGORY_CONF_KEYS[c] for c in categories}
    fields = {}
    for category, key in keys.items():
        # Bewusst geleerte Auswahl (Schlüssel vorhanden, aber []) respektieren statt sie beim
        # erneuten Öffnen der Einstellungen wieder mit "alle Ziele" vorzubelegen - siehe
        # targets_for_category() in notify_util.py für dieselbe Unterscheidung beim Versand.
        # Zusätzlich auf die aktuell gewählten Ziele einschränken: fielen die Ziele zwischenzeitlich
        # unter zwei (Feld verschwand aus dem Formular) und wurden dann anders wieder aufgefüllt,
        # könnte die gespeicherte Auswahl sonst Ziele enthalten, die gar nicht mehr zur Wahl stehen -
        # als Default für den Selector ungültig, und irreführend beim erneuten Öffnen.
        default = [t for t in d[key] if t in current] if key in d else current
        fields[vol.Optional(key, default=default)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=options, multiple=True, mode=selector.SelectSelectorMode.LIST)
        )
    return fields


def _weekend_quiet_fields(d: dict) -> dict:
    g = d.get
    return {
        vol.Required(
            CONF_QUIET_WEEKEND_DIFFERENT, default=g(CONF_QUIET_WEEKEND_DIFFERENT, False)
        ): bool,
        vol.Required(
            CONF_QUIET_START_WEEKEND, default=g(CONF_QUIET_START_WEEKEND, g(CONF_QUIET_START, DEFAULT_QUIET_START))
        ): selector.TimeSelector(),
        vol.Required(
            CONF_QUIET_END_WEEKEND, default=g(CONF_QUIET_END_WEEKEND, g(CONF_QUIET_END, DEFAULT_QUIET_END))
        ): selector.TimeSelector(),
    }


def _current_notify(d: dict) -> list[str]:
    targets = d.get(CONF_NOTIFY_SERVICES)
    if targets is None:
        legacy = (d.get(CONF_NOTIFY_SERVICE) or "").strip()
        targets = [legacy] if legacy.startswith("notify.") else []
    return list(targets)


# Beim Kopieren einer Raum-Vorlage nicht übernehmen: eindeutig diesem einen Raum zugeordnete
# Entitäten. Alles andere (Außensensoren, Schwellwerte, Benachrichtigungen, ...) darf gerne
# übernommen werden - oft dieselben Werte im ganzen Haus bzw. bewusst gewählte Vorlieben.
TEMPLATE_STRIP = {
    CONF_NAME, CONF_WINDOW, CONF_INDOOR_TEMP, CONF_INDOOR_HUMIDITY, CONF_INDOOR_RH, CONF_CO2, CONF_SHOWER,
    # Eigene Geräte des Quell-Raums - sonst würde der neue Raum unbemerkt das Thermostat, den
    # Entfeuchter oder das Rollo eines ANDEREN Raums mitsteuern, statt nur unverfängliche Werte
    # wie Schwellen oder Außensensoren zu übernehmen.
    CONF_CLIMATES, CONF_DEHUMIDIFIER, CONF_SHUTTER,
    # Ohne das würde ein von der Vorlage übernommener Zielwert bei unverändert übernommenem Feld
    # NICHT als "unangetastet" erkannt (das prüft async_step_room nur gegen DEFAULT_TARGET_ABS),
    # wodurch der zum tatsächlich gewählten Raumtyp passende Richtwert nie automatisch gesetzt
    # würde, wenn sich der Raumtyp vom Quell-Raum unterscheidet (z. B. Vorlage "Bad" -> neuer Raum
    # "Schlafzimmer"). Ohne Vorlage bleibt das Feld leer und async_step_room setzt ohnehin den
    # zum gewählten Raumtyp passenden Wert.
    CONF_TARGET_ABS,
}


def _room_templates(hass: HomeAssistant) -> dict[str, str]:
    """{entry_id: Raumname} aller bestehenden Räume, für die Vorlagen-Auswahl beim Einrichten."""
    return {
        e.entry_id: e.data.get(CONF_NAME, e.title)
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ROOM
    }


def _template_data(hass: HomeAssistant, entry_id: str) -> dict:
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if not entry:
        return {}
    data = {**entry.data, **entry.options}
    return {k: v for k, v in data.items() if k not in TEMPLATE_STRIP}


def _windows(d: dict) -> list[str]:
    value = d.get(CONF_WINDOW)
    if isinstance(value, str):
        return [value] if value else []
    return list(value or [])


# ----------------------------------------------------------------------
# Felder je Bereich
# ----------------------------------------------------------------------
def _section_fields(name: str, hass: HomeAssistant, d: dict, with_name: bool) -> dict:
    sensor = _entity("sensor")
    g = d.get

    if name == "room":
        fields = {}
        if with_name:
            fields[_req(CONF_NAME, g(CONF_NAME))] = str
        fields.update({
            _req(CONF_WINDOW, _windows(d)): _entity(["binary_sensor", "sensor"], multiple=True),
            vol.Required(CONF_VOLUME, default=g(CONF_VOLUME, 40.0)): _number(1, 2000, 0.1, "m³"),
            vol.Required(CONF_WINDOW_DIRECTION, default=g(CONF_WINDOW_DIRECTION, 180)): _number(0, 359, 1, "°"),
            vol.Required(CONF_ROOM_TYPE, default=g(CONF_ROOM_TYPE, DEFAULT_ROOM_TYPE)): _select(
                list(ROOM_TYPE_TARGET_ABS), "room_type"
            ),
            vol.Required(CONF_BUILDING, default=g(CONF_BUILDING, DEFAULT_BUILDING)): _select(
                list(U_VALUES), "building_standard"
            ),
        })
        return fields

    if name == "indoor":
        return {
            _req(CONF_INDOOR_TEMP, g(CONF_INDOOR_TEMP)): sensor,
            _req(CONF_INDOOR_HUMIDITY, g(CONF_INDOOR_HUMIDITY)): sensor,
            _opt(CONF_INDOOR_RH, g(CONF_INDOOR_RH)): sensor,
            _opt(CONF_CO2, g(CONF_CO2)): sensor,
            _opt(CONF_SHOWER, g(CONF_SHOWER)): _entity(["binary_sensor", "input_boolean"]),
            vol.Required(CONF_SHOWER_DETECT, default=g(CONF_SHOWER_DETECT, False)): bool,
        }

    if name == "outdoor":
        return {
            _req(CONF_OUTDOOR_TEMP, g(CONF_OUTDOOR_TEMP)): sensor,
            _req(CONF_OUTDOOR_HUMIDITY, g(CONF_OUTDOOR_HUMIDITY)): sensor,
            _opt(CONF_OUTDOOR_RH, g(CONF_OUTDOOR_RH)): sensor,
            _req(CONF_RAIN, g(CONF_RAIN)): _entity(["binary_sensor", "sensor"]),
            _req(CONF_WIND_SPEED, g(CONF_WIND_SPEED)): sensor,
            _req(CONF_WIND_DIRECTION, g(CONF_WIND_DIRECTION)): sensor,
            vol.Required(CONF_WIND_IS_FROM, default=g(CONF_WIND_IS_FROM, True)): bool,
            _opt(CONF_WEATHER, g(CONF_WEATHER)): _entity("weather"),
            vol.Required(CONF_USE_SUN, default=g(CONF_USE_SUN, True)): bool,
            vol.Required(CONF_SUN_ENTITY, default=g(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)): _entity("sun"),
            vol.Required(
                CONF_MIN_SUN_ELEVATION, default=g(CONF_MIN_SUN_ELEVATION, DEFAULT_MIN_SUN_ELEVATION)
            ): _number(0, 90, 1, "°"),
            _opt(CONF_SOLAR_RADIATION, g(CONF_SOLAR_RADIATION)): sensor,
            _opt(CONF_THUNDERSTORM, g(CONF_THUNDERSTORM)): _entity(["binary_sensor", "sensor"]),
            _opt(CONF_WIND_GUST, g(CONF_WIND_GUST)): sensor,
            _opt(CONF_FROST, g(CONF_FROST)): _entity(["binary_sensor", "sensor"]),
        }

    if name == "behavior":
        return {
            vol.Required(CONF_SEASON_MODE, default=g(CONF_SEASON_MODE, DEFAULT_SEASON_MODE)): _select(
                [SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER], "season_mode"
            ),
            vol.Required(
                CONF_SEASON_THRESHOLD, default=g(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD)
            ): _number(5, 25, 0.5, "°C"),
            vol.Required(CONF_TARGET_ABS, default=g(CONF_TARGET_ABS, DEFAULT_TARGET_ABS)): _number(5, 20, 0.1, "g/m³"),
            vol.Required(
                CONF_HUMID_HYSTERESIS, default=g(CONF_HUMID_HYSTERESIS, DEFAULT_HUMID_HYSTERESIS)
            ): _number(0, 2, 0.05, "g/m³"),
            vol.Required(CONF_MAX_TEMP_DIFF, default=g(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)): _number(0, 30, 0.5, "°C"),
            vol.Required(CONF_COMFORT_TEMP, default=g(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)): _number(16, 30, 0.5, "°C"),
            vol.Required(
                CONF_PREHEAT_TEMP, default=g(CONF_PREHEAT_TEMP, DEFAULT_PREHEAT_TEMP)
            ): _number(10, 25, 0.5, "°C"),
            vol.Required(CONF_COOL_LIMIT, default=g(CONF_COOL_LIMIT, DEFAULT_COOL_LIMIT)): _number(0, 25, 0.5, "°C"),
        }

    if name == "notify":
        current = _current_notify(d)
        fields = {
            vol.Optional(CONF_NOTIFY_SERVICES, default=current): _notify_selector(hass, current),
            _opt(CONF_PERSONS, g(CONF_PERSONS, [])): _entity("person", multiple=True),
            vol.Required(CONF_QUIET_START, default=g(CONF_QUIET_START, DEFAULT_QUIET_START)): selector.TimeSelector(),
            vol.Required(CONF_QUIET_END, default=g(CONF_QUIET_END, DEFAULT_QUIET_END)): selector.TimeSelector(),
        }
        fields.update(_weekend_quiet_fields(d))
        fields.update({
            vol.Required(
                CONF_NOTIFICATION_COOLDOWN, default=g(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
            ): _number(5, 1440, 5, "min"),
            vol.Required(CONF_WEEKLY_REPORT, default=g(CONF_WEEKLY_REPORT, True)): bool,
            vol.Required(CONF_MONTHLY_REPORT, default=g(CONF_MONTHLY_REPORT, True)): bool,
            _opt(CONF_VACATION, g(CONF_VACATION)): _entity(["calendar", "input_boolean", "binary_sensor"]),
            _opt(CONF_VACATION_KEYWORD, g(CONF_VACATION_KEYWORD)): str,
        })
        fields.update(_category_fields(d, current))
        return fields

    if name == "devices":
        return {
            _opt(CONF_CLIMATES, g(CONF_CLIMATES, [])): _entity("climate", multiple=True),
            _opt(CONF_DEHUMIDIFIER, g(CONF_DEHUMIDIFIER)): _entity(["switch", "humidifier"]),
            _opt(CONF_SHUTTER, g(CONF_SHUTTER)): _entity("cover"),
            vol.Required(CONF_ENERGY_PRICE, default=g(CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE)): _number(0, 2, 0.01, "€/kWh"),
        }

    raise ValueError(name)


def room_schema(hass: HomeAssistant, d: dict, setup: bool) -> vol.Schema:
    """Ein Formular, jeder Bereich aufklappbar."""
    return vol.Schema({
        vol.Required(name): section(
            vol.Schema(_section_fields(name, hass, d, with_name=setup)),
            {"collapsed": not (setup and name in OPEN_ON_SETUP)},
        )
        for name in SECTIONS
    })


def overview_schema(hass: HomeAssistant, d: dict) -> vol.Schema:
    current = _current_notify(d)
    messages = {
        vol.Required(CONF_COMBINE, default=d.get(CONF_COMBINE, True)): bool,
        vol.Optional(CONF_NOTIFY_SERVICES, default=current): _notify_selector(hass, current),
        _opt(CONF_PERSONS, d.get(CONF_PERSONS, [])): _entity("person", multiple=True),
        vol.Required(CONF_QUIET_START, default=d.get(CONF_QUIET_START, DEFAULT_QUIET_START)): selector.TimeSelector(),
        vol.Required(CONF_QUIET_END, default=d.get(CONF_QUIET_END, DEFAULT_QUIET_END)): selector.TimeSelector(),
    }
    messages.update(_weekend_quiet_fields(d))
    messages[vol.Required(
        CONF_NOTIFICATION_COOLDOWN, default=d.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
    )] = _number(5, 1440, 5, "min")
    messages.update(_category_fields(d, current, categories=(CAT_REMINDER, CAT_REPORT)))
    reports = {
        vol.Required(CONF_WEEKLY_REPORT, default=d.get(CONF_WEEKLY_REPORT, True)): bool,
        vol.Required(CONF_MONTHLY_REPORT, default=d.get(CONF_MONTHLY_REPORT, True)): bool,
    }
    return vol.Schema({
        vol.Required("messages"): section(vol.Schema(messages), {"collapsed": False}),
        vol.Required("reports"): section(vol.Schema(reports), {"collapsed": False}),
    })


def flatten(user_input: dict) -> dict:
    """{bereich: {feld: wert}} -> {feld: wert}; entfernte optionale Felder leer speichern."""
    data = {}
    for key, value in user_input.items():
        if (key in SECTIONS or key in OVERVIEW_SECTIONS) and isinstance(value, dict):
            data.update(value)
        else:
            data[key] = value
    for key, empty in OPTIONAL_EMPTY.items():
        data.setdefault(key, empty)
    data[CONF_NOTIFY_SERVICE] = ""  # altes Textfeld aus Version < 1.7 ablösen
    return data


# ----------------------------------------------------------------------
# Einrichtung
# ----------------------------------------------------------------------
class SmartVentilationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        options = ["room", "overview"]
        if _room_templates(self.hass):
            # Nur anbieten, wenn es überhaupt einen Raum gibt, der als Vorlage dienen könnte.
            options.append("room_from_template")
        return self.async_show_menu(step_id="user", menu_options=options)

    async def async_step_room(self, user_input=None):
        if user_input is not None:
            data = flatten(user_input)
            await self.async_set_unique_id(data[CONF_NAME].strip().lower())
            self._abort_if_unique_id_configured()
            data[CONF_ENTRY_TYPE] = ENTRY_TYPE_ROOM
            # Tagesziel unangetastet gelassen (zeigte nur den allgemeinen Vorschlag) ->
            # stattdessen den zum gewählten Raumtyp passenden Richtwert übernehmen.
            # Ein bewusst abweichend eingetragener Wert bleibt unangetastet.
            if data.get(CONF_TARGET_ABS) == DEFAULT_TARGET_ABS:
                data[CONF_TARGET_ABS] = ROOM_TYPE_TARGET_ABS.get(
                    data.get(CONF_ROOM_TYPE), DEFAULT_TARGET_ABS
                )
            return self.async_create_entry(title=data[CONF_NAME], data=data)
        # getattr, weil das Feld nur gesetzt ist, wenn man über "Raum aus Vorlage" hierherkam
        return self.async_show_form(
            step_id="room", data_schema=room_schema(self.hass, getattr(self, "_template", {}), setup=True)
        )

    async def async_step_room_from_template(self, user_input=None):
        """Einstellungen eines bestehenden Raums übernehmen (Außensensoren, Schwellwerte,
        Benachrichtigungen, ...) - nur Name und raumeigene Sensoren bleiben leer."""
        if user_input is not None:
            self._template = _template_data(self.hass, user_input.get("vorlage") or "")
            return await self.async_step_room()
        templates = _room_templates(self.hass)
        options = [selector.SelectOptionDict(value=entry_id, label=name) for entry_id, name in templates.items()]
        schema = vol.Schema({
            vol.Required("vorlage"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
        })
        return self.async_show_form(step_id="room_from_template", data_schema=schema)

    async def async_step_overview(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id("overview")
            self._abort_if_unique_id_configured()
            data = flatten(user_input)
            data[CONF_ENTRY_TYPE] = ENTRY_TYPE_OVERVIEW
            data[CONF_NAME] = "Lüften Übersicht"
            return self.async_create_entry(title="Lüften Übersicht", data=data)
        return self.async_show_form(step_id="overview", data_schema=overview_schema(self.hass, {}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartVentilationOptionsFlow()


# ----------------------------------------------------------------------
# Einstellungen: ein Formular, einmal speichern
# ----------------------------------------------------------------------
class SmartVentilationOptionsFlow(config_entries.OptionsFlow):
    """Einstellungen nachträglich ändern – das Gelernte bleibt erhalten."""

    async def async_step_init(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        overview = self.config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_OVERVIEW

        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **flatten(user_input)}
            )

        schema = overview_schema(self.hass, current) if overview else room_schema(self.hass, current, setup=False)
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={"name": str(current.get(CONF_NAME, ""))},
        )
