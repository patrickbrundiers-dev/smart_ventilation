"""Einrichtung als Assistent (Raum oder Übersicht), Optionen als Menü."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
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
    CONF_SEASON_MODE, CONF_SEASON_THRESHOLD, DEFAULT_SEASON_MODE, DEFAULT_SEASON_THRESHOLD,
    SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER, CONF_WEATHER, CONF_COOL_LIMIT,
    DEFAULT_COOL_LIMIT, CONF_QUIET_START, CONF_QUIET_END, DEFAULT_QUIET_START,
    DEFAULT_QUIET_END, CONF_CLIMATES, CONF_CO2, CONF_BUILDING, DEFAULT_BUILDING, U_VALUES,
    CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE, CONF_PERSONS, CONF_ENTRY_TYPE,
    ENTRY_TYPE_ROOM, ENTRY_TYPE_OVERVIEW, CONF_COMBINE, CONF_SHOWER, CONF_SHOWER_DETECT,
    CONF_VACATION, CONF_VACATION_KEYWORD, CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP,
    CONF_DEHUMIDIFIER, CONF_WEEKLY_REPORT,
)

ROOM_SECTIONS = ["sensors", "behavior", "notify", "heating"]

# Optionale Felder je Abschnitt: werden beim Speichern geleert, wenn der Nutzer sie entfernt
OPTIONAL_KEYS = {
    "sensors": {CONF_CO2: "", CONF_WEATHER: "", CONF_SHOWER: ""},
    "behavior": {CONF_VACATION: "", CONF_VACATION_KEYWORD: ""},
    "notify": {CONF_NOTIFY_SERVICES: [], CONF_PERSONS: []},
    "heating": {CONF_CLIMATES: [], CONF_DEHUMIDIFIER: ""},
    "overview": {CONF_NOTIFY_SERVICES: [], CONF_PERSONS: []},
}


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def _entity(domain, multiple=False):
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    )


def _req(key, value):
    """Pflichtfeld – nur vorbelegen, wenn es einen Wert gibt."""
    return vol.Required(key, default=value) if value not in (None, "", []) else vol.Required(key)


def _opt(key, value):
    """Optionales Feld – Vorschlag statt Default, damit es sich leeren lässt."""
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
    services = sorted(
        set(services) | set(current),
        key=lambda s: (not s.startswith("notify.mobile_app_"), s),
    )
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


def _select(options, key):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, translation_key=key, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


# ----------------------------------------------------------------------
# Formulare je Abschnitt
# ----------------------------------------------------------------------
def schema_sensors(d: dict, with_name: bool) -> vol.Schema:
    sensor = _entity(["sensor"])
    fields = {}
    if with_name:
        fields[_req(CONF_NAME, d.get(CONF_NAME, "Schlafzimmer"))] = str
    fields.update({
        _req(CONF_WINDOW, _windows(d)): _entity(["binary_sensor", "sensor"], multiple=True),
        _req(CONF_INDOOR_HUMIDITY, d.get(CONF_INDOOR_HUMIDITY)): sensor,
        _req(CONF_INDOOR_TEMP, d.get(CONF_INDOOR_TEMP)): sensor,
        _req(CONF_OUTDOOR_HUMIDITY, d.get(CONF_OUTDOOR_HUMIDITY)): sensor,
        _req(CONF_OUTDOOR_TEMP, d.get(CONF_OUTDOOR_TEMP)): sensor,
        _req(CONF_WIND_SPEED, d.get(CONF_WIND_SPEED)): sensor,
        _req(CONF_WIND_DIRECTION, d.get(CONF_WIND_DIRECTION)): sensor,
        vol.Required(CONF_WIND_IS_FROM, default=d.get(CONF_WIND_IS_FROM, True)): bool,
        _req(CONF_RAIN, d.get(CONF_RAIN)): _entity(["binary_sensor", "sensor"]),
        _opt(CONF_CO2, d.get(CONF_CO2)): sensor,
        _opt(CONF_WEATHER, d.get(CONF_WEATHER)): _entity("weather"),
        _opt(CONF_SHOWER, d.get(CONF_SHOWER)): _entity(["binary_sensor", "input_boolean"]),
        vol.Required(CONF_SHOWER_DETECT, default=d.get(CONF_SHOWER_DETECT, False)): bool,
        vol.Required(CONF_VOLUME, default=d.get(CONF_VOLUME, 44.8)): vol.All(
            vol.Coerce(float), vol.Range(min=1, max=2000)
        ),
        vol.Required(CONF_WINDOW_DIRECTION, default=d.get(CONF_WINDOW_DIRECTION, 106)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=360)
        ),
    })
    return vol.Schema(fields)


def schema_behavior(d: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_TARGET_ABS, default=d.get(CONF_TARGET_ABS, DEFAULT_TARGET_ABS)): vol.All(
            vol.Coerce(float), vol.Range(min=5, max=20)
        ),
        vol.Required(CONF_SEASON_MODE, default=d.get(CONF_SEASON_MODE, DEFAULT_SEASON_MODE)): _select(
            [SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER], "season_mode"
        ),
        vol.Required(
            CONF_SEASON_THRESHOLD, default=d.get(CONF_SEASON_THRESHOLD, DEFAULT_SEASON_THRESHOLD)
        ): vol.All(vol.Coerce(float), vol.Range(min=5, max=25)),
        vol.Required(CONF_MAX_TEMP_DIFF, default=d.get(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=30)
        ),
        vol.Required(CONF_BUILDING, default=d.get(CONF_BUILDING, DEFAULT_BUILDING)): _select(
            list(U_VALUES), "building_standard"
        ),
        vol.Required(CONF_COOL_LIMIT, default=d.get(CONF_COOL_LIMIT, DEFAULT_COOL_LIMIT)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=25)
        ),
        vol.Required(CONF_COMFORT_TEMP, default=d.get(CONF_COMFORT_TEMP, DEFAULT_COMFORT_TEMP)): vol.All(
            vol.Coerce(float), vol.Range(min=16, max=30)
        ),
        _opt(CONF_VACATION, d.get(CONF_VACATION)): _entity(["calendar", "input_boolean", "binary_sensor"]),
        _opt(CONF_VACATION_KEYWORD, d.get(CONF_VACATION_KEYWORD)): str,
        vol.Required(CONF_USE_SUN, default=d.get(CONF_USE_SUN, True)): bool,
        vol.Required(
            CONF_MIN_SUN_ELEVATION, default=d.get(CONF_MIN_SUN_ELEVATION, DEFAULT_MIN_SUN_ELEVATION)
        ): vol.All(vol.Coerce(float), vol.Range(min=0, max=90)),
        vol.Required(CONF_SUN_ENTITY, default=d.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)): _entity("sun"),
    })


def schema_notify(hass: HomeAssistant, d: dict, with_combine: bool = False) -> vol.Schema:
    current = _current_notify(d)
    fields = {}
    if with_combine:
        fields[vol.Required(CONF_COMBINE, default=d.get(CONF_COMBINE, True))] = bool
    fields.update({
        vol.Optional(CONF_NOTIFY_SERVICES, default=current): _notify_selector(hass, current),
        vol.Required(CONF_WEEKLY_REPORT, default=d.get(CONF_WEEKLY_REPORT, True)): bool,
        _opt(CONF_PERSONS, d.get(CONF_PERSONS, [])): _entity("person", multiple=True),
        vol.Required(
            CONF_NOTIFICATION_COOLDOWN, default=d.get(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN)
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Required(CONF_QUIET_START, default=d.get(CONF_QUIET_START, DEFAULT_QUIET_START)): selector.TimeSelector(),
        vol.Required(CONF_QUIET_END, default=d.get(CONF_QUIET_END, DEFAULT_QUIET_END)): selector.TimeSelector(),
    })
    return vol.Schema(fields)


def schema_heating(d: dict) -> vol.Schema:
    return vol.Schema({
        _opt(CONF_CLIMATES, d.get(CONF_CLIMATES, [])): _entity("climate", multiple=True),
        _opt(CONF_DEHUMIDIFIER, d.get(CONF_DEHUMIDIFIER)): _entity(["switch", "humidifier"]),
        vol.Required(CONF_ENERGY_PRICE, default=d.get(CONF_ENERGY_PRICE, DEFAULT_ENERGY_PRICE)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2)
        ),
    })


def _fill_optional(section: str, user_input: dict) -> dict:
    data = dict(user_input)
    for key, empty in OPTIONAL_KEYS.get(section, {}).items():
        data.setdefault(key, empty)
    if section == "notify":
        data[CONF_NOTIFY_SERVICE] = ""  # altes Textfeld ablösen
    return data


# ----------------------------------------------------------------------
# Einrichtung
# ----------------------------------------------------------------------
class SmartVentilationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["sensors", "overview"])

    # --- Raum: vier Schritte ---
    async def async_step_sensors(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME].strip().lower())
            self._abort_if_unique_id_configured()
            self._data.update(_fill_optional("sensors", user_input))
            self._data[CONF_ENTRY_TYPE] = ENTRY_TYPE_ROOM
            return await self.async_step_behavior()
        return self.async_show_form(step_id="sensors", data_schema=schema_sensors(self._data, True))

    async def async_step_behavior(self, user_input=None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()
        return self.async_show_form(step_id="behavior", data_schema=schema_behavior(self._data))

    async def async_step_notify(self, user_input=None):
        if user_input is not None:
            self._data.update(_fill_optional("notify", user_input))
            return await self.async_step_heating()
        return self.async_show_form(step_id="notify", data_schema=schema_notify(self.hass, self._data))

    async def async_step_heating(self, user_input=None):
        if user_input is not None:
            self._data.update(_fill_optional("heating", user_input))
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="heating", data_schema=schema_heating(self._data))

    # --- Übersicht ---
    async def async_step_overview(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id("overview")
            self._abort_if_unique_id_configured()
            data = _fill_optional("overview", user_input)
            data[CONF_ENTRY_TYPE] = ENTRY_TYPE_OVERVIEW
            data[CONF_NAME] = "Lüften Übersicht"
            return self.async_create_entry(title="Lüften Übersicht", data=data)
        return self.async_show_form(
            step_id="overview", data_schema=schema_notify(self.hass, {}, with_combine=True)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartVentilationOptionsFlow()


# ----------------------------------------------------------------------
# Optionen: Menü, jeder Abschnitt wird sofort gespeichert
# ----------------------------------------------------------------------
class SmartVentilationOptionsFlow(config_entries.OptionsFlow):
    """Einstellungen nachträglich ändern – das Gelernte bleibt erhalten."""

    @property
    def _current(self) -> dict:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def _is_overview(self) -> bool:
        return self.config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_OVERVIEW

    def _save(self, section: str, user_input: dict):
        options = {**self.config_entry.options, **_fill_optional(section, user_input)}
        return self.async_create_entry(title="", data=options)

    async def async_step_init(self, user_input=None):
        if self._is_overview:
            return await self.async_step_overview()
        return self.async_show_menu(step_id="init", menu_options=ROOM_SECTIONS)

    async def async_step_sensors(self, user_input=None):
        if user_input is not None:
            return self._save("sensors", user_input)
        return self.async_show_form(step_id="sensors", data_schema=schema_sensors(self._current, False))

    async def async_step_behavior(self, user_input=None):
        if user_input is not None:
            return self._save("behavior", user_input)
        return self.async_show_form(step_id="behavior", data_schema=schema_behavior(self._current))

    async def async_step_notify(self, user_input=None):
        if user_input is not None:
            return self._save("notify", user_input)
        return self.async_show_form(step_id="notify", data_schema=schema_notify(self.hass, self._current))

    async def async_step_heating(self, user_input=None):
        if user_input is not None:
            return self._save("heating", user_input)
        return self.async_show_form(step_id="heating", data_schema=schema_heating(self._current))

    async def async_step_overview(self, user_input=None):
        if user_input is not None:
            return self._save("overview", user_input)
        return self.async_show_form(
            step_id="overview", data_schema=schema_notify(self.hass, self._current, with_combine=True)
        )
