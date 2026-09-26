from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN, CONF_NAME, CONF_VOLUME, CONF_WINDOW_DIRECTION,
    CONF_INDOOR_HUMIDITY, CONF_OUTDOOR_HUMIDITY,
    CONF_INDOOR_TEMP, CONF_OUTDOOR_TEMP, CONF_WIND_SPEED,
    CONF_WIND_DIRECTION, CONF_WIND_IS_FROM, CONF_RAIN, CONF_WINDOW,
    CONF_MAX_TEMP_DIFF, CONF_USE_SUN, CONF_MIN_SUN_ELEVATION,
    CONF_SUN_ENTITY, DEFAULT_MAX_TEMP_DIFF, DEFAULT_MIN_SUN_ELEVATION,
    DEFAULT_SUN_ENTITY, DEFAULT_NOTIFICATION_COOLDOWN,
    CONF_NOTIFY_SERVICE, CONF_NOTIFICATION_COOLDOWN,
    CONF_TARGET_ABS, DEFAULT_TARGET_ABS,
)


def _schema(defaults: dict, include_name: bool) -> vol.Schema:
    """Gemeinsames Formular für Einrichtung und Optionen."""
    d = defaults.get
    entity = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
    )
    sun_entity = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["sun"])
    )

    fields = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default=d(CONF_NAME, "Schlafzimmer"))] = str

    def ent(key):
        # Bei Optionen den bisherigen Wert vorbelegen
        return vol.Required(key, default=d(key)) if d(key) else vol.Required(key)

    fields.update({
        vol.Required(CONF_VOLUME, default=d(CONF_VOLUME, 44.8)): vol.Coerce(float),
        vol.Required(CONF_WINDOW_DIRECTION, default=d(CONF_WINDOW_DIRECTION, 106)): vol.Coerce(float),

        ent(CONF_INDOOR_HUMIDITY): entity,
        ent(CONF_OUTDOOR_HUMIDITY): entity,
        ent(CONF_INDOOR_TEMP): entity,
        ent(CONF_OUTDOOR_TEMP): entity,
        ent(CONF_WIND_SPEED): entity,
        ent(CONF_WIND_DIRECTION): entity,
        ent(CONF_RAIN): entity,
        ent(CONF_WINDOW): entity,

        vol.Required(
            CONF_TARGET_ABS, default=d(CONF_TARGET_ABS, DEFAULT_TARGET_ABS)
        ): vol.All(vol.Coerce(float), vol.Range(min=5, max=20)),

        vol.Required(CONF_WIND_IS_FROM, default=d(CONF_WIND_IS_FROM, True)): bool,
        vol.Required(
            CONF_MAX_TEMP_DIFF, default=d(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)
        ): vol.Coerce(float),
        vol.Required(CONF_USE_SUN, default=d(CONF_USE_SUN, True)): bool,
        vol.Required(
            CONF_MIN_SUN_ELEVATION,
            default=d(CONF_MIN_SUN_ELEVATION, DEFAULT_MIN_SUN_ELEVATION),
        ): vol.Coerce(float),
        vol.Required(
            CONF_SUN_ENTITY, default=d(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        ): sun_entity,

        # Optional, z. B. notify.mobile_app_patrick – leer = keine Push-Nachrichten
        vol.Optional(CONF_NOTIFY_SERVICE, default=d(CONF_NOTIFY_SERVICE, "")): str,
        vol.Required(
            CONF_NOTIFICATION_COOLDOWN,
            default=d(CONF_NOTIFICATION_COOLDOWN, DEFAULT_NOTIFICATION_COOLDOWN),
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
    })
    return vol.Schema(fields)


class SmartVentilationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME].strip().lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        return self.async_show_form(step_id="user", data_schema=_schema({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartVentilationOptionsFlow()


class SmartVentilationOptionsFlow(config_entries.OptionsFlow):
    """Einstellungen nachträglich ändern – das Gelernte bleibt erhalten."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(current, False)
        )
