"""Benachrichtigungen: Alexa bekommt einen vorlesbaren Text mit Raum, Handys Titel + Aktionen."""
from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.smart_ventilation import notify_util


def test_speech_text_room_first_and_units() -> None:
    text = notify_util.speech_text(
        "Lüftung abgeschlossen: Schlafzimmer",
        "Erfolgreich. Dauer: 6.5 Minuten. Feuchteunterschied: 3.2 → 1.1 g/m³ (66% reduziert).",
    )
    assert text == (
        "Schlafzimmer, Lüftung abgeschlossen. Erfolgreich. Dauer, 6,5 Minuten. "
        "Feuchteunterschied, 3,2 auf 1,1 Gramm pro Kubikmeter, 66 Prozent reduziert."
    )
    assert notify_util.speech_text("Raum kühlt aus: Küche", "Nur noch 16.4 °C – bitte schließen.") == (
        "Küche, Raum kühlt aus. Nur noch 16,4 Grad, bitte schließen."
    )


def test_speech_text_overview_list() -> None:
    assert notify_util.speech_text("Lüften: 2 Räume", "• Bad: Stoßlüften 8 Min.\n• Küche: Querlüften 4 Min.") == (
        "Lüften, 2 Räume. Bad, Stoßlüften 8 Minuten. Küche, Querlüften 4 Minuten."
    )


async def test_send_voice_and_phone(hass: HomeAssistant) -> None:
    calls: dict[str, list[dict]] = {}

    def register(name):
        async def handler(call: ServiceCall) -> None:
            calls.setdefault(name, []).append(dict(call.data))
        hass.services.async_register("notify", name, handler)

    register("alexa_media_kueche")
    register("mobile_app_pixel")
    sent = await notify_util.send(
        hass,
        ["notify.alexa_media_kueche", "notify.mobile_app_pixel", "notify.gibt_es_nicht"],
        "Lüften: Wohnzimmer",
        "Jetzt wäre ein guter Zeitpunkt zum Lüften – Stoßlüften, voraussichtlich 5 Minuten.",
        "tag1",
        actions=[{"action": "x", "title": "Später"}],
    )
    await hass.async_block_till_done()
    assert sent
    alexa = calls["alexa_media_kueche"][0]
    assert alexa["data"] == {"type": "tts"} and "title" not in alexa
    assert alexa["message"].startswith("Wohnzimmer, Lüften. ")
    phone = calls["mobile_app_pixel"][0]
    assert phone["title"] == "Lüften: Wohnzimmer"
    assert phone["data"] == {"tag": "tag1", "actions": [{"action": "x", "title": "Später"}]}
