"""Registrierung der Dashboard-Karte als Ressource (wie HACS)."""
from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

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


async def test_switch_to_local_and_remove_duplicates(hass: HomeAssistant) -> None:
    res = FakeResources([
        {"id": "1", "type": "module", "url": f"{card.CARD_URL}?v=2.3.2"},
        {"id": "2", "type": "module", "url": "/hacsfiles/other-card.js"},
        {"id": "3", "type": "module", "url": f"{card.LOCAL_URL}?v=2.3.2"},
    ])
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=res)
    assert await card._async_register_resource(hass, card.LOCAL_URL_VERSIONED)
    assert res.items == [
        {"id": "1", "type": "module", "url": card.LOCAL_URL_VERSIONED},
        {"id": "2", "type": "module", "url": "/hacsfiles/other-card.js"},
    ]


class _NoDashboardConfig:
    async def async_load(self, force):
        raise HomeAssistantError("keine Konfiguration")


async def test_real_resource_collection(hass: HomeAssistant) -> None:
    """Gegen die echte Ressourcen-Sammlung von Home Assistant."""
    coll = ResourceStorageCollection(hass, _NoDashboardConfig())
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=coll)
    assert await card._async_register_resource(hass, card.CARD_URL_VERSIONED)
    assert await card._async_register_resource(hass, card.LOCAL_URL_VERSIONED)
    assert [(i["type"], i["url"]) for i in coll.async_items()] == [("module", card.LOCAL_URL_VERSIONED)]
    await card.async_remove_resource(hass)
    assert coll.async_items() == []


def test_copy_to_www(tmp_path) -> None:
    dest = tmp_path / "www" / "smart_ventilation" / card.FILE_NAME
    assert card._copy_to_www(card.CARD_FILE, dest)
    assert dest.read_bytes() == card.CARD_FILE.read_bytes()
    mtime = dest.stat().st_mtime_ns
    assert card._copy_to_www(card.CARD_FILE, dest)       # unverändert -> nicht neu schreiben
    assert dest.stat().st_mtime_ns == mtime
    assert not (dest.parent / (dest.stem + ".tmp")).exists()


def test_local_served_detection(tmp_path) -> None:
    """Erkennt, ob Home Assistant /local/ ausliefert (echter aiohttp-Router)."""
    from aiohttp import web
    from homeassistant.components.http.static import CachingStaticResource

    app = web.Application()
    fake = SimpleNamespace(http=SimpleNamespace(app=app))
    assert card._local_served(fake) is False
    app.router.register_resource(CachingStaticResource("/local", str(tmp_path)))
    assert card._local_served(fake) is True
    assert card._local_served(SimpleNamespace(http=None)) is False
