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
    CONF_INDOOR_HUMIDITY, CONF_OUTDOOR_HUMIDITY, CONF_INDOOR_TEMP, CONF_OUTDOOR_TEMP,
    CONF_WIND_SPEED, CONF_WIND_DIRECTION, CONF_WIND_IS_FROM, CONF_RAIN, CONF_WINDOW,
    CONF_MAX_TEMP_DIFF, CONF_USE_SUN, CONF_MIN_SUN_ELEVATION, CONF_SUN_ENTITY,
    DEFAULT_MAX_TEMP_DIFF, DEFAULT_MIN_SUN_ELEVATION, DEFAULT_SUN_ENTITY,
    DEFAULT_NOTIFICATION_COOLDOWN, CONF_NOTIFY_SERVICE, CONF_NOTIFY_SERVICES,
    CONF_NOTIFICATION_COOLDOWN, CONF_TARGET_ABS, DEFAULT_TARGET_ABS,
    CONF_ROOM_TYPE, DEFAULT_ROOM_TYPE, ROOM_TYPE_TARGET_ABS,
    CONF_SEASON_MODE, CONF_SEASON_THRESHOLD, DEFAULT_SEASON_MODE, DEFAULT_SEASON_THRESHOLD,
    SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER, CONF_WEATHER, CONF_COOL_LIMIT,
    DEFAULT_COOL_LIMIT, CONF_QUIET_START, CONF_QUIET_END, DEFAULT_QUIET_START,
    DEFAULT_QUIET_END, CONF_CLIMATES, CONF_CO2, CONF_BUILDING, DEFAULT_BUILDING, U_VALUES,
    CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE, CONF_PERSONS, CONF_ENTRY_TYPE,
    ENTRY_TYPE_ROOM, ENTRY_TYPE_OVERVIEW, CONF_COMBINE, CONF_SHOWER, CONF_SHOWER_DETECT,
    CONF_VACATION, CONF_VACATION_KEYWORD, CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP,
    CONF_DEHUMIDIFIER, CONF_WEEKLY_REPORT, CONF_MONTHLY_REPORT,
)

# Reihenfolge der Bereiche im Formular
SECTIONS = ["room", "indoor", "outdoor", "behavior", "notify", "devices", "advanced"]
OVERVIEW_SECTIONS = ["messages", "reports"]
# Bei der Ersteinrichtung offen (enthalten Pflichtfelder), der Rest zugeklappt
OPEN_ON_SETUP = {"room", "indoor", "outdoor"}

# Optionale Felder: werden leer gespeichert, wenn der Nutzer sie entfernt
OPTIONAL_EMPTY = {
    CONF_CO2: "", CONF_SHOWER: "", CONF_WEATHER: "", CONF_VACATION: "",
    CONF_VACATION_KEYWORD: "", CONF_NOTIFY_SERVICES: [], CONF_PERSONS: [],
    CONF_CLIMATES: [], CONF_DEHUMIDIFIER: "",
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


def _current_notify(d: dict) -> list[str]:
    targets = d.get(CONF_NOTIFY_SERVICES)
    if targets is None:
        legacy = (d.get(CONF_NOTIFY_SERVICE) or "").strip()
        targets = [legacy] if legacy.startswith("notify.") else []
    return list(targets)


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
        })
        return fields

    if name == "indoor":
        return {
            _req(CONF_INDOOR_TEMP, g(CONF_INDOOR_TEMP)): sensor,
            _req(CONF_INDOOR_HUMIDITY, g(CONF_INDOOR_HUMIDITY)): sensor,
            _opt(CONF_CO2, g(CONF_CO2)): sensor,
            _opt(CONF_SHOWER, g(CONF_SHOWER)): _entity(["binary_sensor", "input_boolean"]),
            vol.Required(CONF_SHOWER_DETECT, default=g(CONF_SHOWER_DETECT, False)): bool,
        }

    if name == "outdoor":
        return {
            _req(CONF_OUTDOOR_TEMP, g(CONF_OUTDOOR_TEMP)): sensor,
            _req(CONF_OUTDOOR_HUMIDITY, g(CONF_OUTDOOR_HUMIDITY)): sensor,
            _req(CONF_RAIN, g(CONF_RAIN)): _entity(["binary_sensor", "sensor"]),
            _req(CONF_WIND_SPEED, g(CONF_WIND_SPEED)): sensor,
            _req(CONF_WIND_DIRECTION, g(CONF_WIND_DIRECTION)): sensor,
            _opt(CONF_WEATHER, g(CONF_WEATHER)): _entity("weather"),
        }

    if name == "behavior":
        return {
            vol.Required(CONF_SEASON_MODE, default=g(CONF_SEASON_MODE, DEFAULT_SEASON_MODE)): _select(
                [SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER], "season_mode"
            ),
            vol.Required(CONF_TARGET_ABS, default=g(CONF_TARGET_ABS, DEFAULT_TARGET_ABS)): _number(5, 20, 0.1, "g/m³"),
            vol.Required(CONF_MAX_TEMP_DIFF, default=g(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)): _number(0, 30, 0.5, "°C"),
            vol.Required(CONF_COMFORT_TEMP, default=g(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)): _number(16, 30, 0.5, "°C"),
            vol.Required(CONF_COOL_LIMIT, default=g(CONF_COOL_LIMIT, DEFAULT_COOL_LIMIT)): _number(0, 25, 0.5, "°C"),
            vol.Required(CONF_BUILDING, default=g(CONF_BUILDING, DEFAULT_BUILDING)): _select(
                list(U_VALUES), "building_standard"
            ),
        }

    if name == "notify":
        current = _current_notify(d)
        return {
            vol.Optional(CONF_NOTIFY_SERVICES, default=current): _notify_selector(hass, current),
            _opt(CONF_PERSONS, g(CONF_PERSONS, [])): _entity("person", multiple=True),
            vol.Required(CONF_QUIET_START, default=g(CONF_QUIET_START, DEFAULT_QUIET_START)): selector.TimeSelector(),
            vol.Required(CONF_QUIET_END, default=g(CONF_QUIET_END, DEFAULT_QUIET_END)): selector.TimeSelector(),
            vol.Required(CONF_WEEKLY_REPORT, default=g(CONF_WEEKLY_REPORT, True)): bool,
            vol.Required(CONF_MONTHLY_REPORT, default=g(CONF_MONTHLY_REPORT, True)): bool,
            _opt(CONF_VACATION, g(CONF_VACATION)): _entity(["calendar", "input_boolean", "binary_sensor"]),
            _opt(CONF_VACATION_KEYWORD, g(CONF_VACATION_KEYWORD)): str,
        }

    if name == "devices":
        return {
            _opt(CONF_CLIMATES, g(CONF_CLIMATES, [])): _entity("climate", multiple=True),
            _opt(CONF_DEHUMIDIFIER, g(CONF_DEHUMIDIFIER)): _entity(["switch", "humidifier"]),
            vol.Required(CONF_ENERGY_PRICE, default=g(CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE)): _number(0, 2, 0.01, "€/kWh"),
        }

    if name == "advanced":
        return {
            vol.Required(
                CONF_SEASON_THRESHOLD, default=g(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD)
            ): _number(5, 25, 0.5, "°C"),
            vol.Required(
                CONF_NOTIFICATION_COOLDOWN, default=g(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
            ): _number(5, 1440, 5, "min"),
            vol.Required(CONF_WIND_IS_FROM, default=g(CONF_WIND_IS_FROM, True)): bool,
            vol.Required(CONF_USE_SUN, default=g(CONF_USE_SUN, True)): bool,
            vol.Required(CONF_SUN_ENTITY, default=g(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)): _entity("sun"),
            vol.Required(
                CONF_MIN_SUN_ELEVATION, default=g(CONF_MIN_SUN_ELEVATION, DEFAULT_MIN_SUN_ELEVATION)
            ): _number(0, 90, 1, "°"),
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
        vol.Required(
            CONF_NOTIFICATION_COOLDOWN, default=d.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
        ): _number(5, 1440, 5, "min"),
    }
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
        return self.async_show_menu(step_id="user", menu_options=["room", "overview"])

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
        return self.async_show_form(step_id="room", data_schema=room_schema(self.hass, {}, setup=True))

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
