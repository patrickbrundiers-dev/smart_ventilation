            return
        limit = 0.5 if self.session.get("cooling") else float(
            self.data.get(CONF_MAX_TEMP_DIFF, DEFAULT_MAX_TEMP_DIFF)
        )
        if to - ti <= limit:
            return
        self._warm_warned = True
        await self._send(
            f"Fenster schließen: {self.data[CONF_NAME]}",
            f"Draußen ist es jetzt {to - ti:.1f} °C wärmer ({to:.1f} °C) als drinnen ({ti:.1f} °C) – "
            "der Raum heizt sich sonst auf.",
            f"smart_ventilation_{self.entry.entry_id}_warm",
            category=CAT_WARNING,
        )

    # ------------------------------------------------------------------
    # Luftentfeuchter
    # ------------------------------------------------------------------
    async def _dehumidifier_control(self, now):
        entity_id = self.data.get(CONF_DEHUMIDIFIER)
        if not entity_id:
            return
        domain = entity_id.partition(".")[0]
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        rh = self.indoor_rh
        # NICHT humidity_difference (Unterschied zur Außenluft) verwenden: Ein Luftentfeuchter
        # entzieht der Raumluft Wasser unabhängig davon, wie feucht es draußen ist - anders als
        # Lüften braucht er keine trockenere Außenluft. Mit dem Außenluft-Vergleich als Gate würde
        # er ausgerechnet dann nicht anspringen, wenn die Außenluft feuchter als drinnen ist -
        # genau der Fall, in dem Lüften nicht hilft und der Entfeuchter am meisten gebraucht wird.
        # self._humidity_reasons_met (siehe _humidity_need) prüft stattdessen, ob die Raumluft für
        # sich genommen zu feucht ist (Zielwert/rel. Feuchte/Schimmelrisiko), unabhängig von außen.
        need = self._humidity_reasons_met
        cannot_vent = (
            bool(self.block_reason)
            or self.recommended_minutes == 0
            or self.in_quiet_hours(now)
            or self.on_vacation
            or (self.persons and not self.anyone_home)
        )

        if self._dehum_on_since is None:
            # Einschalten: feucht, Lüften geht gerade nicht, Fenster zu
            if (
                need and cannot_vent and not self.open_windows()
                and (
                    (rh is not None and rh >= DEHUM_ON_RH)
                    or _num_state(self.hass, self.data[CONF_INDOOR_HUMIDITY])
                    >= float(self.data.get("target_absolute_humidity", 11.5))
                )
                and state.state == "off"
            ):
                if await self._call(domain, "turn_on", {"entity_id": entity_id}):
                    self._dehum_on_since = now
                    await self._save()
            return

        # Ausschalten: sobald ein Fenster geöffnet wird (dann übernimmt das Lüften, und
        # Entfeuchten + offenes Fenster wäre nur verschwendete Energie) - die Mindestlaufzeit