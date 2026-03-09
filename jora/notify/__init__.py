from __future__ import annotations

from typing import TYPE_CHECKING

from jora.notify.checks import diff
from jora.notify.send import send

if TYPE_CHECKING:
    from jora.state import State

_prev: State | None = None


def run(state: State):
    """Compare current state against previous and send OS notifications."""
    global _prev

    if _prev is not None:
        for msg in diff(_prev, state):
            send(msg)

    _prev = state
