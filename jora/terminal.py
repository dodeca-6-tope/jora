"""Low-level terminal: alt screen, raw mode, input, rendering."""

import atexit
import os
import select
import sys
import termios
import tty


class Terminal:
    """Context manager for full-screen terminal UI sessions."""

    def __init__(self):
        self._fd = None
        self._saved = None
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def __enter__(self):
        self._fd = sys.stdin.fileno()
        self._saved = termios.tcgetattr(self._fd)
        self._enter_raw()
        self._active = True
        sys.stdout.write("\033[?1049h\033[?25l\033[?1004h")
        sys.stdout.flush()
        atexit.register(self.cleanup)
        return self

    def __exit__(self, *_):
        self.cleanup()

    def cleanup(self):
        """Leave alt screen, show cursor, restore terminal."""
        if not self._active:
            return
        self._active = False
        sys.stdout.write("\033[?1004l\033[?25h\033[?1049l")
        sys.stdout.flush()
        self._restore()

    def suspend(self):
        """Leave alt screen and restore terminal for a child process."""
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
        self._restore()

    def resume(self):
        """Re-enter alt screen and raw mode after a child process."""
        self._enter_raw()
        sys.stdout.write("\033[?1049h\033[?25l")
        sys.stdout.flush()

    def readkey(self) -> str | None:
        """Read a single keypress. Returns None on timeout (1/60s)."""
        if not select.select([self._fd], [], [], 1 / 60)[0]:
            return None
        ch = os.read(self._fd, 1)
        if ch == b"\x1b":
            if select.select([self._fd], [], [], 0.02)[0]:
                seq = os.read(self._fd, 16)
                if seq[:2] == b"[A":
                    return "up"
                if seq[:2] == b"[B":
                    return "down"
                if seq[:2] == b"[C":
                    return "right"
                if seq[:2] == b"[D":
                    return "left"
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

    def render(self, lines: list[str]):
        """Write full screen with synchronized update to avoid flicker."""
        buf = "\033[?2026h\033[H"
        for line in lines:
            buf += line + "\033[K\n"
        buf += "\033[J\033[?2026l"
        sys.stdout.buffer.write(buf.encode())
        sys.stdout.buffer.flush()

    def _enter_raw(self):
        """Switch to raw mode, re-enable output processing for \\n → \\r\\n."""
        tty.setraw(self._fd)
        attrs = termios.tcgetattr(self._fd)
        attrs[1] |= termios.OPOST
        termios.tcsetattr(self._fd, termios.TCSADRAIN, attrs)

    def _restore(self):
        """Restore saved terminal attributes."""
        if self._saved:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
