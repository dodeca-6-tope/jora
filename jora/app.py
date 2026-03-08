"""Terminal: alt screen, input, rendering."""

import atexit
import os
import select
import sys
import termios
import tty
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from jora.actions.clean import Clean
from jora.actions.delete import Delete
from jora.actions.fix import Fix
from jora.actions.kill import Kill
from jora.actions.open import Open
from jora.actions.pr import PR
from jora.actions.quit import Quit
from jora.actions.refresh import Refresh
from jora.actions.select import Select
from jora.help import render_help
from jora.notifications import Notifications


@dataclass
class Row:
    key: str
    title: str
    wt_key: str = ""
    marks: Tuple[str, ...] = ()
    worktree: bool = False
    session: bool = False
    data: object = None
    actions: list = field(default_factory=list)


@dataclass
class Section:
    rows: List[Row] = field(default_factory=list)
    subtitle: str = ""

_TASK_ACTIONS = [Select(), Fix(), Kill(), Open(), PR()]
_REVIEW_ACTIONS = [Select(), Kill(), Delete(), PR()]

_GLOBAL_ACTIONS = [Refresh(), Clean(), Quit()]


def actions_for(row):
    return _GLOBAL_ACTIONS + (row.actions if row else [])


def dispatch(key, row, state):
    """Dispatch key to matching action. Returns 'exit' to quit."""
    if not key:
        return
    for action in actions_for(row):
        if action.matches(key) and action.enabled(state, row):
            try:
                return action.run(state, row)
            except Exception as e:
                state.on_alert(f"Error: {e}")
                return

_saved = None
_active = False
_fd = None

# -- ANSI --------------------------------------------------------------------

_FAINT = "\033[38;5;252m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_ITALIC = "\033[3m"
_REVERSE = "\033[7m"
_RESET = "\033[0m"
_SPINNER = r"-\|/"
_PREFIX = 17  # visible chars before title: "> ● ● LTXD-408 ◆ "
_CURSOR = ">"

_MARK = {
    "ok": f"{_GREEN}●{_RESET}",
    "fail": f"{_RED}●{_RESET}",
    "neutral": f"{_YELLOW}●{_RESET}",
}


# -- Data types (view model) -------------------------------------------------


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
    sys.stdout.write("\033[?1049h\033[?25l\033[?1004h")
    sys.stdout.flush()
    atexit.register(_cleanup)


def _cleanup():
    global _active
    if not _active:
        return
    _active = False
    sys.stdout.write("\033[?1004l\033[?25h\033[?1049l")
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
            if seq[:2] == b"[A":
                return "up"
            if seq[:2] == b"[B":
                return "down"
            if seq[:2] in (b"[C", b"[D"):
                return None
            if seq[:2] == b"[I":
                return "focus"
            if seq[:2] == b"[O":
                return None
        return "esc"
    if ch == b"\t":
        return "tab"
    if ch in (b"\r", b"\n"):
        return "enter"
    if ch == b"\x03":
        raise KeyboardInterrupt
    return ch.decode("utf-8", errors="ignore")


# -- Rendering ---------------------------------------------------------------


def _format_row(row: Row, selected: bool) -> str:
    wt = "◆" if row.session else ("◇" if row.worktree else f"{_FAINT}◇{_RESET}")
    title = row.title
    avail = os.get_terminal_size().columns - _PREFIX
    if avail > 3 and len(title) > avail:
        title = title[: avail - 3] + "..."
    cur = _CURSOR if selected else " "
    marks = " ".join(_MARK.get(m, _MARK["neutral"]) for m in row.marks) if row.marks else f"{_FAINT}○ ○{_RESET}"
    return f"{cur} {marks} {row.key} {wt} {title}"


def _render(lines: list[str]):
    buf = "\033[?2026h\033[H"
    for line in lines:
        buf += line + "\033[K\n"
    buf += "\033[J\033[?2026l"
    sys.stdout.buffer.write(buf.encode())
    sys.stdout.buffer.flush()


# -- App --------------------------------------------------------------------


def _item_to_row(item, actions):
    marks = ()
    if item.review_status:
        marks = (item.review_status, item.ci_status)
    key = str(item.number) if hasattr(item, "number") else item.id[:9]
    return Row(
        key=key,
        title=item.title,
        wt_key=item.id.lower(),
        marks=marks,
        worktree=item.worktree,
        session=item.session,
        data=item,
        actions=actions,
    )


def _rebuild_tab(tab, items):
    rows = [_item_to_row(item, tab.actions) for item in items]
    tab.sections = [Section(rows=rows, subtitle=tab.subtitle)]


@dataclass
class Tab:
    name: str
    actions: list
    subtitle: str
    sections: List[Section] = field(default_factory=list)
    cursor: int = 0


@dataclass
class App:
    state: object = None
    _notifications: Notifications = field(default_factory=Notifications)
    _tabs: List[Tab] = field(default_factory=lambda: [
        Tab("Tasks", _TASK_ACTIONS, "No tasks"),
        Tab("Reviews", _REVIEW_ACTIONS, "Nothing to review"),
    ])
    _tab_idx: int = 0
    _spin: int = 0

    @property
    def tabs(self):
        return self._tabs

    @property
    def active_tab(self):
        return self._tab_idx

    @property
    def tab(self):
        return self._tabs[self._tab_idx]

    @property
    def sections(self):
        return self.tab.sections

    def rebuild(self):
        """Rebuild all tabs from current state data."""
        if not self.state:
            return
        _rebuild_tab(self._tabs[0], self.state.task_items())
        _rebuild_tab(self._tabs[1], self.state.review_items())

    def next_tab(self):
        self._tab_idx = (self._tab_idx + 1) % len(self._tabs)

    def alert(self, text: str):
        self._notifications.add(text)

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
        _, prev = self._at(self.tab.cursor)
        if prev:
            found = self._index_of_key(prev.key)
            if found is not None:
                self.tab.cursor = found
                return
        self.tab.cursor = max(0, min(self.tab.cursor, total - 1))

    def tick(self) -> Tuple[Optional[str], Optional[Row]]:
        """Draw, read one key, return (key, row) or (None, None) on no input."""
        total = self._total_rows
        self.stabilize_cursor()

        if self.state and self.state.loading:
            self._spin += 1

        self._draw()

        key = _readkey()
        if key is None:
            return None, None

        if key == "up" and total:
            self.tab.cursor = max(0, self.tab.cursor - 1)
            return None, None
        if key == "down" and total:
            self.tab.cursor = min(total - 1, self.tab.cursor + 1)
            return None, None

        _, row = self._at(self.tab.cursor)
        return key, row

    def _draw(self):
        loading = self.state.loading if self.state else False
        spinner_ch = _SPINNER[self._spin // 3 % len(_SPINNER)] if loading else " "

        # Full-screen spinner for operations with text
        if loading and self.state.loading_text:
            _render([f"{self.state.loading_text} {spinner_ch}"])
            return

        # Header: title + spinner slot + tab bar
        tab_bar = ""
        if self._tabs:
            parts = []
            for i, tab in enumerate(self._tabs):
                if i == self._tab_idx:
                    parts.append(f"{_REVERSE}{tab.name}{_RESET}")
                else:
                    parts.append(tab.name)
            tab_bar = " · ".join(parts)
        # Extra space keeps spinner visually separate from tabs
        lines = [f"{_BOLD}Jora{_RESET} {spinner_ch}  {tab_bar}", ""]

        # Sections and rows
        flat_idx = 0
        for i, sec in enumerate(self.sections):
            if i > 0:
                lines.append("")
            if sec.subtitle and not sec.rows and not loading:
                lines.append(f"  {_ITALIC}{sec.subtitle}{_RESET}")
            for row in sec.rows:
                lines.append(_format_row(row, flat_idx == self.tab.cursor))
                flat_idx += 1

        # Help bar
        _, cur_row = self._at(self.tab.cursor)
        if self.state:
            parts = []
            if len(self._tabs) > 1:
                parts.append("[⇥] switch")
            help_text = render_help(actions_for(cur_row), self.state, cur_row)
            if help_text:
                parts.append(help_text)
            if parts:
                lines.append("")
                lines.append("  ".join(parts))
        msgs = self._notifications.active()
        if msgs:
            lines.append("")
            lines.extend(msgs)
        _render(lines)


def pick(title: str, items: List[str]) -> Optional[int]:
    """Minimal picker. Returns selected index or None if cancelled.
    Works both standalone and inside an active App.
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
            cur = _CURSOR if i == cursor else " "
            lines.append(f"{cur} {item}")
        lines.append("")
        lines.append("[\u23ce] select  [esc] back")
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
