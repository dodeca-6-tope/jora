"""Terminal: alt screen, input, rendering."""

import atexit
import select
import sys
import termios
import tty

_saved = None
_active = False


def init():
    global _saved, _active
    _saved = termios.tcgetattr(sys.stdin)
    _active = True
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    atexit.register(cleanup)


def cleanup():
    global _active
    if not _active:
        return
    _active = False
    sys.stdout.write("\033[?25h\033[?1049l")
    sys.stdout.flush()
    if _saved:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _saved)


def readkey() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = select.select([fd], [], [], 1 / 60)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return {"[A": "up", "[B": "down"}.get(seq, "esc")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def render(lines: list[str]):
    """Overwrite screen in place (flicker-free)."""
    buf = "\033[H"
    for line in lines:
        buf += line + "\033[K\n"
    buf += "\033[J"
    sys.stdout.write(buf)
    sys.stdout.flush()
