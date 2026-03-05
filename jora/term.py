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
    worktree: bool = False
    session: bool = False
    data: object = None  # opaque payload for action handlers


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
    actions: list = field(default_factory=list)

    @property
    def help(self) -> str:
        return "  ".join(f"{a.key} {a.label}" for a in self.actions)


@dataclass
class Menu:
    sections: List[Section] = field(default_factory=list)
    loading: bool = False
    message: str = ""
    _cursor: int = 0
    _spin: int = 0

    def __enter__(self):
        _init()
        return self

    def __exit__(self, *_):
        _cleanup()

    @property
    def _total_rows(self) -> int:
        return sum(len(sec.rows) for sec in self.sections)

    def _selected_section(self) -> Optional[Section]:
        idx = self._cursor
        for sec in self.sections:
            if idx < len(sec.rows):
                return sec
            idx -= len(sec.rows)
        return None

    def _selected_row(self) -> Optional[Row]:
        idx = self._cursor
        for sec in self.sections:
            if idx < len(sec.rows):
                return sec.rows[idx]
            idx -= len(sec.rows)
        return None

    def tick(self) -> Optional[str]:
        """Draw, read one key, return key or None. Handles navigation internally."""
        total = self._total_rows
        if total:
            self._cursor = max(0, min(self._cursor, total - 1))

        if self.loading:
            self._spin += 1

        self._draw()

        key = _readkey()
        if key is None:
            return None

        self.message = ""

        if key == "up" and total:
            self._cursor = max(0, self._cursor - 1)
            return None
        if key == "down" and total:
            self._cursor = min(total - 1, self._cursor + 1)
            return None

        return key

    @property
    def selected(self) -> int:
        return self._cursor

    def run_blocking(self, text: str, fn: Callable, inline: bool = False):
        """Run fn() in a background thread with a spinner. Returns result or raises.

        If inline=False (default), replaces screen with spinner.
        If inline=True, shows spinner in header while keeping the menu visible.
        """
        result = [None]
        error = [None]

        def work():
            try:
                result[0] = fn()
            except Exception as e:
                error[0] = e

        prev_loading = self.loading
        prev_message = self.message
        t = threading.Thread(target=work, daemon=True)
        t.start()
        frame = 0
        while t.is_alive():
            frame += 1
            if inline:
                self.loading = True
                self._spin += 1
                self.message = text
                self._draw()
            else:
                _render([f"{text} {_SPINNER[frame // 4 % len(_SPINNER)]}"])
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
            for row in sec.rows:
                lines.append(_format_row(row, flat_idx == self._cursor))
                flat_idx += 1
        sec = self._selected_section()
        if sec:
            lines.append("")
            lines.append(f"{_DIM}{sec.help}{_RESET}")
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
        lines.append(f"{_DIM}\u23ce select  esc back{_RESET}")
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
        elif key in ("enter", "s"):
            return cursor
        elif key in ("esc", "q"):
            return None
