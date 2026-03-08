import time
from typing import List

_TTL = 2  # seconds before a notification auto-clears


class Notifications:
    def __init__(self):
        self._items: List[tuple[str, float]] = []

    def add(self, text: str):
        self._items.insert(0, (text, time.monotonic()))

    def active(self) -> List[str]:
        now = time.monotonic()
        self._items = [(t, ts) for t, ts in self._items if now - ts < _TTL]
        return [t for t, _ in self._items]
