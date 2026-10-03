from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.smart_ventilation.notify_util import (
    load_notification_guard,
    notification_guard_key,
    release_notification,
    reserve_notification,
)


def test_notification_guard_blocks_identical_repeat():
    guard = {}
    now = dt_util.now()
    key = notification_guard_key("reminder", "Lüften: Wohnzimmer")

    assert reserve_notification(guard, key, now, 3600)
    assert not reserve_notification(guard, key, now + timedelta(minutes=5), 3600)


def test_notification_guard_survives_persistence_roundtrip():
    now = dt_util.now()
    key = notification_guard_key("reminder", "Lüften: Bad")
    guard = {}
    assert reserve_notification(guard, key, now, 3600)

    restored = load_notification_guard(guard)
    assert not reserve_notification(restored, key, now + timedelta(minutes=10), 3600)


def test_notification_guard_allows_after_cooldown():
    guard = {}
    now = dt_util.now()
    key = notification_guard_key("reminder", "Lüften: Küche")

    assert reserve_notification(guard, key, now, 60)
    assert reserve_notification(guard, key, now + timedelta(seconds=61), 60)


def test_notification_guard_allows_priority_escalation():
    guard = {}
    now = dt_util.now()
    key = notification_guard_key("mold", "Schimmel: Schlafzimmer")

    assert reserve_notification(guard, key, now, 3600, priority=1)
    assert reserve_notification(guard, key, now + timedelta(minutes=1), 3600, priority=2)


def test_notification_guard_release_allows_retry_after_failed_send():
    guard = {}
    now = dt_util.now()
    key = notification_guard_key("shower", "Nach dem Duschen: Bad")

    assert reserve_notification(guard, key, now, 3600)
    release_notification(guard, key)
    assert reserve_notification(guard, key, now + timedelta(seconds=1), 3600)


def test_notification_guard_survives_clock_moving_backward():
    """Eine rückwärts springende Uhr (NTP-Korrektur, DST-Umstellung) darf eine Benachrichtigung
    nicht unbegrenzt unterdrücken - vorher wurde eine negative "elapsed"-Zeit fälschlich als
    "noch in der Abklingzeit" gewertet (negativ ist immer < cooldown_seconds)."""
    guard = {}
    now = dt_util.now()
    key = notification_guard_key("reminder", "Lüften: Flur")

    assert reserve_notification(guard, key, now, 3600)
    # Die Uhr springt 5 Minuten zurück - die "neue" Zeit liegt VOR der gespeicherten Reservierung.
    assert reserve_notification(guard, key, now - timedelta(minutes=5), 3600)


def test_notification_guard_different_rooms_do_not_collide():
    """Zwei inhaltlich unterschiedliche Sammel-Benachrichtigungen dürfen sich nicht gegenseitig
    blockieren, nur weil sie (zufällig) denselben generischen Titel haben (z. B. "Lüften: 2
    Räume" für zwei verschiedene Raum-Kombinationen) - der Dedup-Schlüssel muss die tatsächliche
    Raum-Identität abbilden, nicht nur den Anzeige-Titel."""
    guard = {}
    now = dt_util.now()
    key_bad_kueche = notification_guard_key("reminder", "bad,küche")
    key_keller_dachboden = notification_guard_key("reminder", "dachboden,keller")

    assert reserve_notification(guard, key_bad_kueche, now, 3600)
    assert reserve_notification(guard, key_keller_dachboden, now + timedelta(minutes=20), 3600)
