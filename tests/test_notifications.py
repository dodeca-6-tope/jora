import time
from unittest.mock import patch

from jora.notifications import Notifications


def test_single_notification():
    n = Notifications()
    n.add("hello")
    assert n.active() == ["hello"]


def test_multiple_notifications_newest_first():
    n = Notifications()
    n.add("first")
    n.add("second")
    assert n.active() == ["second", "first"]


def test_expired_notifications_removed():
    n = Notifications()
    n.add("old")
    with patch("jora.notifications.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 10
        assert n.active() == []


def test_partial_expiry():
    now = time.monotonic()
    n = Notifications()
    n.add("old")
    with patch("jora.notifications.time") as mock_time:
        # Advance past TTL so "old" expires, then add "new"
        mock_time.monotonic.return_value = now + 10
        n.add("new")
        assert n.active() == ["new"]
