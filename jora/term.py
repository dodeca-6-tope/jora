"""Terminal: alt screen, input, rendering."""

import atexit
import os
import select
import sys
import termios
import threading
import tty
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

_saved = None
_active = False
_fd = None

# -- ANSI --------------------------------------------------------------------

_DIM = "\033[90m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
_SPINNER = r"-\|/"
_PREFIX = 16  # visible chars before title: "> ✓ ✗ LTXD-408* "

_MARK = {
    "ok": f"{_GREEN}✓{_RESET}",
    "fail": f"{_RED}✗{_RESET}",
    "neutral": f"{_DIM}-{_RESET}",
}


# -- Data types (view model) -------------------------------------------------

@dataclass
class Row:
    key: str
    title: str
    marks: Tuple[str, ...] = ()  # "ok", "fail", "neutral"
    active: bool = False


# -- Setup / teardown --------------------------------------------------------

def _init():
    global _saved, _active, _fd
    _fd = sys.stdin.fileno()
    _saved = termios.tcgetattr(_fd)
    tty.setraw(_fd)
    # Re-enable output processing so \n produces \r\n
    attrs = termios.tcgetattr(_fd)
    attrs[1] |= termios.OPOST
    termios.tcsetattr(_fd, termios.TCSADRAIN, attrs)
    _active = True
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    atexit.register(_cleanup)


def _cleanup():
    global _active
    if not _active:
        return
    _active = False
    sys.stdout.write("\033[?25h\033[?1049l")
    sys.stdout.flush()
    if _saved:
        termios.tcsetattr(_fd, termios.TCSADRAIN, _saved)


# -- Input -------------------------------------------------------------------

def _readkey() -> str:
    ready, _, _ = select.select([_fd], [], [], 1 / 60)
    if not ready:
        return None
    ch = os.read(_fd, 1)
    if ch == b"\x1b":
        # Wait briefly for escape sequence bytes; bare ESC returns immediately
        if select.select([_fd], [], [], 0.02)[0]:
            seq = os.read(_fd, 16)
            if seq[:2] == b"[A": return "up"
            if seq[:2] == b"[B": return "down"
        return "esc"
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b"\x03":
        raise KeyboardInterrupt
    return ch.decode("utf-8", errors="ignore")


# -- Rendering ---------------------------------------------------------------

def _format_marks(marks: Tuple[str, ...]) -> str:
    if not marks:
        return "   "
    return " ".join(_MARK.get(m, _MARK["neutral"]) for m in marks)


def _format_row(row: Row, selected: bool) -> str:
    star = "*" if row.active else ""
    key = f"{row.key}{star}"
    ident = f"{_DIM}{key:<10}{_RESET}"
    title = row.title
    avail = os.get_terminal_size().columns - _PREFIX
    if avail > 3 and len(title) > avail:
        title = title[: avail - 3] + "..."
    cur = ">" if selected else " "
    return f"{cur} {_format_marks(row.marks)} {ident}{title}"


def _render(lines: list[str]):
    buf = "\033[?2026h\033[H"
    for line in lines:
        buf += line + "\033[K\n"
    buf += "\033[J\033[?2026l"
    sys.stdout.buffer.write(buf.encode())
    sys.stdout.buffer.flush()


# -- Menu --------------------------------------------------------------------

_KEY_TO_ACTION = {
    "enter": "select", "s": "select",
    "o": "open", "p": "pr", "r": "refresh",
    "q": "quit", "esc": "quit",
}


@dataclass
class Menu:
    rows: List[Row] = field(default_factory=list)
    loading: bool = False
    message: str = ""
    _cursor: int = 0
    _spin: int = 0

    def __enter__(self):
        _init()
        return self

    def __exit__(self, *_):
        _cleanup()

    def tick(self) -> Optional[str]:
        """Draw, read one key, return action or None."""
        if self.rows:
            self._cursor = max(0, min(self._cursor, len(self.rows) - 1))

        if self.loading:
            self._spin += 1

        self._draw()

        key = _readkey()
        if key is None:
            return None

        self.message = ""

        if key == "up" and self.rows:
            self._cursor = max(0, self._cursor - 1)
            return None
        if key == "down" and self.rows:
            self._cursor = min(len(self.rows) - 1, self._cursor + 1)
            return None

        return _KEY_TO_ACTION.get(key)

    @property
    def selected(self) -> int:
        return self._cursor

    def run_blocking(self, text: str, fn: Callable) -> str:
        """Run fn() in a background thread with a spinner. Returns result or 'Error: ...'."""
        result = [None]
        error = [None]

        def work():
            try:
                result[0] = fn()
            except Exception as e:
                error[0] = str(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        frame = 0
        while t.is_alive():
            frame += 1
            _render([f"{text} {_SPINNER[frame // 4 % len(_SPINNER)]}"])
            t.join(timeout=1 / 60)

        if result[0] is not None:
            return str(result[0])
        return f"Error: {error[0]}"

    def _draw(self):
        spinner = f" {_DIM}{_SPINNER[self._spin // 4 % len(_SPINNER)]}{_RESET}" if self.loading else ""
        lines = [f"{_BOLD}Jora{_RESET} — {len(self.rows)} tasks{spinner}", ""]
        for i, row in enumerate(self.rows):
            lines.append(_format_row(row, i == self._cursor))
        if self.rows:
            lines.append("")
            lines.append(f"{_DIM}⏎ switch  o open  p PR  r refresh  q quit{_RESET}")
        if self.message:
            lines.append("")
            lines.append(self.message)
        _render(lines)
