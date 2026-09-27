"""Registrierung der Dashboard-Karte als Ressource (wie HACS)."""
from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

from custom_components.smart_ventilation import card


class FakeResources:
    """Verhält sich wie die Ressourcen-Sammlung der Dashboards (Speichermodus)."""

    def __init__(self, items=None):
        self.items = list(items or [])
        self.loaded = False

    async def async_get_info(self):
        self.loaded = True
        return {"resources": len(self.items)}

    def async_items(self):
        return self.items

    async def async_create_item(self, data):
        item = {"id": str(len(self.items) + 1), "type": data["res_type"], "url": data["url"]}
        self.items.append(item)
        return item

    async def async_update_item(self, item_id, updates):
        for item in self.items:
            if item["id"] == item_id:
                item.update(url=updates["url"], type=updates["res_type"])
        return item

    async def async_delete_item(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]


async def test_resource_created_once(hass: HomeAssistant) -> None:
    res = FakeResources([{"id": "1", "type": "module", "url": "/hacsfiles/other-card.js"}])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=res)
    assert await card._async_register_resource(hass)
    assert await card._async_register_resource(hass)          # zweimal -> kein Duplikat
    ours = [i for i in res.items if i["url"].startswith(card.CARD_URL)]
    assert len(ours) == 1 and ours[0]["url"] == card.CARD_URL_VERSIONED and ours[0]["type"] == "module"
    assert len(res.items) == 2                                   # fremde Ressource unangetastet


async def test_resource_version_updated(hass: HomeAssistant) -> None:
    res = FakeResources([{"id": "7", "type": "module", "url": f"{card.CARD_URL}?v=0.0.1"}])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=res)
    assert await card._async_register_resource(hass)
    assert res.items == [{"id": "7", "type": "module", "url": card.CARD_URL_VERSIONED}]


async def test_resource_removed(hass: HomeAssistant) -> None:
    res = FakeResources([{"id": "7", "type": "module", "url": card.CARD_URL_VERSIONED},
                         {"id": "8", "type": "module", "url": "/local/x.js"}])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=res)
    await card.async_remove_resource(hass)
    assert res.items == [{"id": "8", "type": "module", "url": "/local/x.js"}]


async def test_yaml_mode_is_skipped(hass: HomeAssistant) -> None:
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=SimpleNamespace(async_items=lambda: []))
    assert await card._async_register_resource(hass) is False
