"""Heizung beim Lüften absenken und danach wiederherstellen.

Eigenes Mixin (bisher Teil von coordinator.py), weil die Heizungs-Hierarchie-Auflösung
(Better Thermostat -> Climate Group Helper/Gruppe -> einzelne Thermostate) ein inhaltlich
abgeschlossener, von der eigentlichen Lüftungsentscheidung unabhängiger Block ist.
"""
from __future__ import annotations

from homeassistant.helpers import entity_registry as er

from .const import HEATING_DELAY_SECONDS


class HeatingMixin:
    """Erwartet die Attribute/Methoden des SmartVentilationCoordinator (u. a. self.hass,
    self.climates, self.session, self.current_duration_seconds, self._call(), self._save())."""

    async def _check_heating(self):
        # Session synchron festhalten: die folgende Schleife wartet auf mehrere echte
        # climate.*-Serviceaufrufe, währenddessen kann das Fenster zugehen (_finish_session setzt
        # self.session dann auf None) oder sogar eine neue Sitzung beginnen - siehe denselben
        # Schutz in _finish_session().
        session = self.session
        if not self.climates or not session or session.get("heating") is not None:
            return
        if self.current_duration_seconds < HEATING_DELAY_SECONDS:
            return

        saved = {}
        external = {}
        for entity_id in self._heating_targets():
            if manager := self._window_managed_by(entity_id):
                external[entity_id] = manager   # regelt selbst beim Fensteröffnen -> nicht eingreifen
                continue
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("off", "unavailable", "unknown"):
                continue
            modes = state.attributes.get("hvac_modes") or []
            if "off" in modes:
                if await self._call("climate", "set_hvac_mode",
                                    {"entity_id": entity_id, "hvac_mode": "off"}):
                    saved[entity_id] = {"mode": state.state}
            else:
                target = state.attributes.get("temperature")
                if target is None:
                    continue
                low = state.attributes.get("min_temp", 7)
                if await self._call("climate", "set_temperature",
                                    {"entity_id": entity_id, "temperature": low}):
                    saved[entity_id] = {"temperature": target}

        if self.session is session:
            session["heating"] = saved
            session["heating_external"] = external
            await self._save()
        else:
            # Die Sitzung wurde inzwischen abgeschlossen oder durch eine neue ersetzt, während wir
            # noch auf die Thermostat-Befehle gewartet haben. _finish_session() kannte "saved" zu
            # dem Zeitpunkt noch nicht (heating war noch None) und konnte die eben abgesenkten
            # Thermostate deshalb nicht wiederherstellen - das holen wir hier nach, statt sie
            # dauerhaft abgesenkt zu lassen.
            await self._restore_heating(saved)

    # --- Heizungs-Hierarchie: Better Thermostat -> (Climate Group Helper / Gruppe) -> Thermostate ---
    def _climate_children(self, entity_id):
        """Direkt untergeordnete Thermostate: bei Better Thermostat die gesteuerten Geräte, bei Gruppen die Mitglieder."""
        bt = self._integration_config(entity_id, "better_thermostat")
        if bt is not None:
            heaters = bt.get("thermostat") or []
            return [h.get("trv") for h in heaters if isinstance(h, dict) and h.get("trv")]
        state = self.hass.states.get(entity_id)
        members = state.attributes.get("entity_id") if state is not None else None
        if isinstance(members, (list, tuple)):
            return [m for m in members if str(m).startswith("climate.")]
        return []

    def _integration_config(self, entity_id, domain):
        """Einstellungen (data + options) der Integration, falls die Entität zu `domain` gehört."""
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry is None or entry.platform != domain or not entry.config_entry_id:
            return None
        config = self.hass.config_entries.async_get_entry(entry.config_entry_id)
        if config is None:
            return None
        return {**config.data, **config.options}

    def _heating_targets(self):
        """Welche Thermostate schalten? Immer die oberste Ebene, jede nur einmal.

        - Liegt ein gewähltes Thermostat/eine Gruppe unter einem Better Thermostat,
          wird das Better Thermostat geschaltet (sonst würde BT dagegen regeln).
        - Ist ein Thermostat Mitglied einer ebenfalls gewählten Gruppe, wird nur die Gruppe geschaltet.
        """
        parent = {}
        for state in self.hass.states.async_all("climate"):
            for child in self._climate_children(state.entity_id):
                # Better Thermostat hat Vorrang als übergeordnete Ebene
                if child not in parent or self._integration_config(state.entity_id, "better_thermostat") is not None:
                    parent[child] = state.entity_id
        selected = set(self.climates)
        result = []
        for entity_id in self.climates:
            chain, node = [], entity_id
            while node in parent and node not in chain:
                chain.append(node)
                node = parent[node]
            chain.append(node)
            ancestors = chain[1:]
            bt = [a for a in ancestors if self._integration_config(a, "better_thermostat") is not None]
            chosen = [a for a in ancestors if a in selected]
            if bt:
                result.append(bt[-1])
            elif chosen:
                result.append(chosen[-1])
            else:
                result.append(entity_id)
        return list(dict.fromkeys(result))

    def _window_managed_by(self, entity_id, _seen=None):
        """Regelt diese Heizung (oder eine Ebene darunter) beim Fensteröffnen selbst?"""
        seen = _seen or set()
        if entity_id in seen:
            return None
        seen.add(entity_id)
        bt = self._integration_config(entity_id, "better_thermostat")
        if bt is not None and bt.get("window_sensors"):
            return "Better Thermostat"
        cgh = self._integration_config(entity_id, "climate_group_helper")
        if cgh is not None and (cgh.get("room_sensor") or cgh.get("zone_sensor")) and str(
            cgh.get("window_mode") or "disabled"
        ) not in ("disabled", "off"):
            return "Climate Group Helper"
        for child in self._climate_children(entity_id):
            if manager := self._window_managed_by(child, seen):
                return manager
        return None

    async def _restore_heating(self, saved):
        for entity_id, before in (saved or {}).items():
            if "mode" in before:
                await self._call("climate", "set_hvac_mode",
                                 {"entity_id": entity_id, "hvac_mode": before["mode"]})
            elif "temperature" in before:
                await self._call("climate", "set_temperature",
                                 {"entity_id": entity_id, "temperature": before["temperature"]})
