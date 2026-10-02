    CO2-Luftqualität pro Raum liefern - sonst müsste man dafür jede Raumkarte einzeln öffnen,
    statt es auf der Übersicht auf einen Blick zu sehen."""
    freezer.move_to("2026-06-15 12:00:00+02:00")
    dehum_calls = async_mock_service(hass, "switch", "turn_on")  # sonst schlägt der Service-Call fehl (kein "switch" geladen)
    hass.states.async_set("switch.entfeuchter", "off")
    hass.states.async_set("sensor.co2", 1500)
    await setup_room(
        hass, use_sun=True, season_mode="summer",
        dehumidifier_entity="switch.entfeuchter", co2_sensor="sensor.co2",
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 40, "azimuth": 106})  # = Fensterausrichtung
    hass.states.async_set("sensor.regen", 1.2)     # Regen -> Lüften blockiert -> Entfeuchter darf ran
    hass.states.async_set("sensor.innen_ah", 12.5)  # feucht genug für den Entfeuchter
    await _tick(hass, freezer, 0.5)
    assert any(call.data.get("entity_id") == ["switch.entfeuchter"] for call in dehum_calls)

    overview = await setup_entry(
        hass, {"entry_type": "overview", "name": "Lüften Übersicht", "combine_notifications": True,
               "notify_services": [], "persons": []}, "overview", "Lüften Übersicht")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    urgent = hass.states.get(eid(hass, "sensor", overview, "most_urgent"))
    room = urgent.attributes["raeume"][0]
    assert room["entfeuchter"] is True
    assert room["rollo_empfehlung"] is True
    assert room["rollo_geschlossen"] is False  # kein Rollo-Entity konfiguriert -> nie "von uns" zu
    assert room["luft"] == "schlecht"


async def test_shutter_recommendation_ignores_heavy_clouds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, berlin
) -> None:
    """Bei bedecktem Himmel darf ein passender Sonnenwinkel allein kein Rollo-Schließen auslösen."""
    freezer.move_to("2026-06-15 12:00:00+02:00")
    entry = await setup_room(hass, use_sun=True, season_mode="summer", weather_entity="weather.home")
    hass.states.async_set(
        "weather.home", "cloudy", {"cloud_coverage": 90, "temperature": 22}
    )
    hass.states.async_set("sun.sun", "above_horizon", {"elevation": 40, "azimuth": 106})
    await hass.async_block_till_done()

    room = hass.data[DOMAIN][entry.entry_id]