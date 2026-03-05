"""Terminal: alt screen, input, rendering."""

import atexit
import os
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from jora.help import format_help

_saved = None
_active = False
_fd = None

# -- ANSI --------------------------------------------------------------------

_DIM = "\033[90m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_BOLD = "\033[1m"
_ITALIC = "\033[3m"
_RESET = "\033[0m"
_SPINNER = r"-\|/"
_PREFIX = 16  # visible chars before title: "> ✓ ✗ LTXD-408* "
_MESSAGE_TTL = 2  # seconds before notification auto-clears

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
    wt_key: str = ""
    marks: Tuple[str, ...] = ()  # "ok", "fail", "neutral"
    worktree: bool = False
    session: bool = False
    data: object = None  # opaque payload for action handlers
    actions: list = field(default_factory=list)


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


def suspend():
    """Leave alt screen and restore terminal for a child process."""
    sys.stdout.write("\033[?25h\033[?1049l")
    sys.stdout.flush()
    if _saved:
        termios.tcsetattr(_fd, termios.TCSADRAIN, _saved)


def resume():
    """Re-enter alt screen and raw mode after a child process."""
    tty.setraw(_fd)
    attrs = termios.tcgetattr(_fd)
    attrs[1] |= termios.OPOST
    termios.tcsetattr(_fd, termios.TCSADRAIN, attrs)
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()


# -- Input -------------------------------------------------------------------

def _readkey() -> Optional[str]:
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
    wt = "◆" if row.session else ("◇" if row.worktree else "")
    key = f"{row.key}{wt}"
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



@dataclass
class Section:
    label: str
    rows: List[Row] = field(default_factory=list)
    subtitle: str = ""


@dataclass
class Menu:
    sections: List[Section] = field(default_factory=list)
    loading: bool = False
    state: object = None
    _message: str = ""
    _message_time: float = 0
    _cursor: int = 0
    _spin: int = 0

    @property
    def message(self) -> str:
        if self._message and self._message_time and time.monotonic() - self._message_time >= _MESSAGE_TTL:
            self._message = ""
        return self._message

    @message.setter
    def message(self, value: str):
        self._message = value
        self._message_time = time.monotonic() if value else 0

    def __enter__(self):
        _init()
        return self

    def __exit__(self, *_):
        _cleanup()

    @property
    def _total_rows(self) -> int:
        return sum(len(sec.rows) for sec in self.sections)

    def _at(self, idx: int) -> Tuple[Optional[Section], Optional[Row]]:
        i = idx
        for sec in self.sections:
            if i < len(sec.rows):
                return sec, sec.rows[i]
            i -= len(sec.rows)
        return None, None

    def _index_of_key(self, key: str) -> Optional[int]:
        idx = 0
        for sec in self.sections:
            for row in sec.rows:
                if row.key == key:
                    return idx
                idx += 1
        return None

    def stabilize_cursor(self):
        """Restore cursor to the previously selected row by key, or clamp."""
        total = self._total_rows
        if not total:
            return
        _, prev = self._at(self._cursor)
        if prev:
            found = self._index_of_key(prev.key)
            if found is not None:
                self._cursor = found
                return
        self._cursor = max(0, min(self._cursor, total - 1))

    def tick(self) -> Tuple[Optional[str], Optional[Section], Optional[Row]]:
        """Draw, read one key, return (key, section, row) or (None, *, *) on no input."""
        total = self._total_rows
        self.stabilize_cursor()

        if self.loading:
            self._spin += 1

        self._draw()

        key = _readkey()
        if key is None:
            return None, None, None

        if key == "up" and total:
            self._cursor = max(0, self._cursor - 1)
            return None, None, None
        if key == "down" and total:
            self._cursor = min(total - 1, self._cursor + 1)
            return None, None, None

        sec, row = self._at(self._cursor)
        return key, sec, row

    def _run_threaded(self, fn):
        result = [None]
        error = [None]
        def work():
            try:
                result[0] = fn()
            except Exception as e:
                error[0] = e
        t = threading.Thread(target=work, daemon=True)
        t.start()
        return t, result, error

    def spin(self, text: str, fn: Callable):
        """Full screen spinner while fn runs."""
        t, result, error = self._run_threaded(fn)
        frame = 0
        while t.is_alive():
            frame += 1
            _render([f"{text} {_SPINNER[frame // 4 % len(_SPINNER)]}"])
            t.join(timeout=1 / 60)
        if error[0] is not None:
            raise error[0]
        return result[0]

    def spin_inline(self, text: str, fn: Callable):
        """Spinner in header while fn runs, menu stays visible."""
        prev_loading = self.loading
        prev_message = self.message
        t, result, error = self._run_threaded(fn)
        while t.is_alive():
            self.loading = True
            self._spin += 1
            self.message = text
            self._draw()
            t.join(timeout=1 / 60)
        self.loading = prev_loading
        self.message = prev_message
        if error[0] is not None:
            raise error[0]
        return result[0]

    def _draw(self):
        spinner = f" {_DIM}{_SPINNER[self._spin // 4 % len(_SPINNER)]}{_RESET}" if self.loading else ""
        lines = [f"{_BOLD}Jora{_RESET}{spinner}", ""]
        flat_idx = 0
        for i, sec in enumerate(self.sections):
            if i > 0:
                lines.append("")
            lines.append(f"  {_DIM}{sec.label}{_RESET}")
            if sec.subtitle and not sec.rows:
                lines.append(f"      {_DIM}{_ITALIC}{sec.subtitle}{_RESET}")
            for row in sec.rows:
                lines.append(_format_row(row, flat_idx == self._cursor))
                flat_idx += 1
        cur_sec, cur_row = self._at(self._cursor)
        if cur_sec and cur_row:
            enabled = [a for a in cur_row.actions if a.enabled(self.state, cur_row)]
            lines.append("")
            lines.append(format_help((a.key, a.label) for a in enabled))
        if self.message:
            lines.append("")
            lines.append(self.message)
        _render(lines)


def pick(title: str, items: List[str]) -> Optional[int]:
    """Minimal picker. Returns selected index or None if cancelled.
    Works both standalone and inside an active Menu.
    """
    owned = not _active
    if owned:
        _init()
    try:
        return _pick_loop(title, items)
    finally:
        if owned:
            _cleanup()


def _pick_loop(title: str, items: List[str]) -> Optional[int]:
    cursor = 0
    while True:
        lines = [f"{_BOLD}{title}{_RESET}", ""]
        for i, item in enumerate(items):
            cur = ">" if i == cursor else " "
            lines.append(f"{cur} {item}")
        lines.append("")
        lines.append(format_help([("\u23ce", "select"), ("esc", "back")]))
        _render(lines)

        try:
            key = _readkey()
        except KeyboardInterrupt:
            return None
        if key is None:
            continue
        if key == "up":
            cursor = max(0, cursor - 1)
        elif key == "down":
            cursor = min(len(items) - 1, cursor + 1)
        elif key == "enter":
            return cursor
        elif key in ("esc", "q"):
            return None
