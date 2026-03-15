"""App: tabs, rows, actions, rendering."""

import os
from dataclasses import dataclass, field

from jora.actions.clean import Clean
from jora.actions.delete import Delete
from jora.actions.kill import Kill
from jora.actions.open import Open
from jora.actions.pr import PR
from jora.actions.quit import Quit
from jora.actions.refresh import Refresh
from jora.actions.select import Select
from jora.notifications import Notifications
from jora.terminal import Terminal
from jora.text import word_wrap


@dataclass
class Row:
    key: str
    title: str
    marks: tuple[str, ...] = ()
    worktree: bool = False
    session: bool = False
    data: object = None
    actions: list = field(default_factory=list)


@dataclass
class Section:
    rows: list[Row] = field(default_factory=list)
    subtitle: str = ""


_TASK_ACTIONS = [Select(), Kill(), Open(), PR()]
_REVIEW_ACTIONS = [Select(), Kill(), Delete(), PR()]

_GLOBAL_ACTIONS = [Refresh(), Clean(), Quit()]


def actions_for(row):
    """Return all actions available for a row (global + row-specific)."""
    return _GLOBAL_ACTIONS + (row.actions if row else [])


def dispatch(key, row, store):
    """Match a keypress to an action and run it. Returns 'exit' to quit."""
    if not key:
        return None
    for action in actions_for(row):
        if action.matches(key) and action.enabled(store, row):
            try:
                return action.run(store, row)
            except Exception as e:
                store.on_alert(f"Error: {e}")
                return None
    return None


term = Terminal()

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


def _format_row(row: Row, selected: bool) -> str:
    """Format a single row line. ◆ = session active, ◇ = worktree exists."""
    wt = "◆" if row.session else ("◇" if row.worktree else f"{_FAINT}◇{_RESET}")
    title = row.title
    avail = os.get_terminal_size().columns - _PREFIX
    if avail > 3 and len(title) > avail:
        title = title[: avail - 3] + "..."
    cur = _CURSOR if selected else " "
    marks = (
        " ".join(_MARK.get(m, _MARK["neutral"]) for m in row.marks)
        if row.marks
        else f"{_FAINT}○ ○{_RESET}"
    )
    return f"{cur} {marks} {row.key} {wt} {title}"


def _item_to_row(item, actions):
    """Convert a TaskItem or ReviewItem to a display Row."""
    marks = ()
    if item.review_status:
        marks = (item.review_status, item.ci_status)
    key = str(item.number) if hasattr(item, "number") else item.id[:9]
    return Row(
        key=key,
        title=item.title,
        marks=marks,
        worktree=item.wt is not None,
        session=item.session,
        data=item,
        actions=actions,
    )


def _rebuild_tab(tab, items):
    """Rebuild a tab's sections from enriched items."""
    rows = [_item_to_row(item, tab.actions) for item in items]
    tab.sections = [Section(rows=rows, subtitle=tab.subtitle)]


@dataclass
class Tab:
    name: str
    actions: list
    subtitle: str
    sections: list[Section] = field(default_factory=list)
    cursor: int = 0


@dataclass
class App:
    store: object
    _notifications: Notifications = field(default_factory=Notifications)
    _tabs: list[Tab] = field(
        default_factory=lambda: [
            Tab("Tasks", _TASK_ACTIONS, "No tasks"),
            Tab("Reviews", _REVIEW_ACTIONS, "Nothing to review"),
        ]
    )
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
        state = self.store.state
        _rebuild_tab(self._tabs[0], state.tasks)
        _rebuild_tab(self._tabs[1], state.reviews)

    def switch_tab(self, delta: int, wrap: bool = False):
        """Move tab index by *delta*, optionally wrapping around."""
        if wrap:
            self._tab_idx = (self._tab_idx + delta) % len(self._tabs)
        else:
            self._tab_idx = max(0, min(self._tab_idx + delta, len(self._tabs) - 1))

    def alert(self, text: str):
        """Add a notification message."""
        self._notifications.add(text)

    def __enter__(self):
        term.__enter__()
        return self

    def __exit__(self, *_):
        term.__exit__()

    @property
    def _total_rows(self) -> int:
        return sum(len(sec.rows) for sec in self.sections)

    def _at(self, idx: int) -> tuple[Section | None, Row | None]:
        """Return the section and row at a flat index across all sections."""
        i = idx
        for sec in self.sections:
            if i < len(sec.rows):
                return sec, sec.rows[i]
            i -= len(sec.rows)
        return None, None

    def _index_of_key(self, key: str) -> int | None:
        """Find the flat index of a row by its key."""
        idx = 0
        for sec in self.sections:
            for row in sec.rows:
                if row.key == key:
                    return idx
                idx += 1
        return None

    def stabilize_cursor(self):
        """Keep cursor on the same row by key after data changes, or clamp."""
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

    def tick(self) -> tuple[str | None, Row | None]:
        """Draw, read one key, return (key, row) or (None, None) on timeout."""
        total = self._total_rows
        self.stabilize_cursor()

        if self.store.loading:
            self._spin += 1

        self._draw()

        key = term.readkey()
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
        """Render the full screen: header, rows, help bar, notifications."""
        spinner_ch = (
            _SPINNER[self._spin // 3 % len(_SPINNER)] if self.store.loading else " "
        )

        if self.store.loading and self.store.loading_text:
            term.render([f"{self.store.loading_text} {spinner_ch}"])
            return

        tab_bar = ""
        if self._tabs:
            parts = []
            for i, tab in enumerate(self._tabs):
                if i == self._tab_idx:
                    parts.append(f"{_REVERSE}{tab.name}{_RESET}")
                else:
                    parts.append(tab.name)
            tab_bar = " · ".join(parts)
        lines = [f"{_BOLD}Jora{_RESET} {spinner_ch}  {tab_bar}", ""]

        flat_idx = 0
        for i, sec in enumerate(self.sections):
            if i > 0:
                lines.append("")
            if sec.subtitle and not sec.rows and not self.store.loading:
                lines.append(f"  {_ITALIC}{sec.subtitle}{_RESET}")
            for row in sec.rows:
                lines.append(_format_row(row, flat_idx == self.tab.cursor))
                flat_idx += 1

        _, cur_row = self._at(self.tab.cursor)
        chunks = []
        if len(self._tabs) > 1:
            chunks.append("[⇥] switch")
        chunks.extend(
            f"[{a.key}] {a.label}"
            for a in actions_for(cur_row)
            if a.enabled(self.store, cur_row)
        )
        if chunks:
            lines.append("")
            lines.extend(word_wrap(chunks, os.get_terminal_size().columns))
        msgs = self._notifications.active()
        if msgs:
            lines.append("")
            lines.extend(msgs)
        term.render(lines)


def pick(title: str, items: list[str]) -> int | None:
    """Show a picker UI. Returns selected index or None if cancelled."""
    owned = not term.active
    if owned:
        term.__enter__()
    try:
        return _pick_loop(title, items)
    finally:
        if owned:
            term.cleanup()


def _pick_loop(title: str, items: list[str]) -> int | None:
    """Picker input loop."""
    cursor = 0
    while True:
        lines = [f"{_BOLD}{title}{_RESET}", ""]
        for i, item in enumerate(items):
            cur = _CURSOR if i == cursor else " "
            lines.append(f"{cur} {item}")
        lines.append("")
        lines.extend(
            word_wrap(["[⏎] select", "[esc] back"], os.get_terminal_size().columns)
        )
        term.render(lines)

        try:
            key = term.readkey()
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
