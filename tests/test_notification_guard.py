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
