from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jora.state import State


def diff(old: State, new: State) -> list[str]:
    return []
