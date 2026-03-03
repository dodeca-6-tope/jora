"""Interactive task picker UI."""

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Dict, List

from jora.git import switch_to_task
from jora.linear import LinearClient
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
import jora.term as term

# -- Colors & symbols --------------------------------------------------------

DIM = "\033[90m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
BG_YELLOW = "\033[103m"
RESET = "\033[0m"
SPINNER = r"-\|/"
_PREFIX = 16  # visible chars before title: "> ● ● LTXD-408  "

# -- Shell init (jora init <shell>) ------------------------------------------

_SHELL_INIT = """\
jora() {
  command jora "$@"
  if [[ -f /tmp/jora_cd ]]; then
    cd "$(cat /tmp/jora_cd)"
    rm /tmp/jora_cd
  fi
}
"""
_SUPPORTED_SHELLS = ("zsh", "bash")

# -- Formatting ---------------------------------------------------------------


def _dot(color_map: Dict[str, str], status: str) -> str:
    color = color_map.get(status)
    return f"{color}●{RESET}" if color else f"{DIM}○{RESET}"


def _pr_indicators(prs: List[Dict]) -> str:
    if not prs:
        return "   "
    pr = prs[0]
    rv = _dot({"APPROVED": GREEN, "CHANGES_REQUESTED": RED}, analyze_reviews(pr.get("reviews", [])))
    ck = _dot({"SUCCESS": GREEN, "FAILURE": RED, "PENDING": YELLOW}, analyze_ci(pr.get("statusCheckRollup", [])))
    return f"{rv} {ck}"


def _format_task(task: Dict, prs: List[Dict], selected: bool, active: bool) -> str:
    """Single task line: cursor, PR indicators, identifier, title."""
    ident_raw = task["identifier"][:9]
    ident = f"{BG_YELLOW}{ident_raw}{RESET}{'':<{9 - len(ident_raw)}}" if active else f"{DIM}{ident_raw:<9}{RESET}"
    title = task.get("title", "No title")
    avail = os.get_terminal_size().columns - _PREFIX
    if avail > 3 and len(title) > avail:
        title = title[: avail - 3] + "..."
    cur = f"{CYAN}>{RESET}" if selected else " "
    return f"{cur} {_pr_indicators(prs)} {ident} {title}"


# -- Screen drawing -----------------------------------------------------------


def _draw(tasks, prs_by_task, cursor, active_key="", message="", spin_frame=-1):
    spinner = f" {DIM}{SPINNER[spin_frame % len(SPINNER)]}{RESET}" if spin_frame >= 0 else ""
    lines = [f"{BOLD}Jora{RESET} — {len(tasks)} tasks{spinner}", ""]
    for i, task in enumerate(tasks):
        active = task["identifier"].lower() == active_key
        lines.append(_format_task(task, prs_by_task.get(task["identifier"], []), i == cursor, active))
    lines.append("")
    lines.append(f"{DIM}⏎ switch · o open · p PR · r refresh · q quit{RESET}")
    if message:
        lines.append("")
        lines.append(message)
    term.render(lines)

# -- Actions ------------------------------------------------------------------


def _detect_active_task() -> str:
    """If cwd is inside a jora worktree, return the task key (lowercase)."""
    cwd = Path.cwd()
    jora_dir = Path.home() / ".jora" / "worktrees"
    return cwd.name if str(cwd).startswith(str(jora_dir)) else ""


def _switch_to_task(task_id: str) -> str:
    """Switch to a task worktree in a background thread with spinner.
    Returns worktree path on success, or an error message string prefixed with 'Error:'."""
    result = [None]
    error = [None]

    def work():
        try:
            result[0] = switch_to_task(task_id)
        except subprocess.CalledProcessError as e:
            error[0] = str(e)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    spin = 0
    while t.is_alive():
        spin += 1
        term.render([f"Switching to {task_id} {SPINNER[spin // 4 % len(SPINNER)]}"])
        t.join(timeout=1 / 60)

    if result[0]:
        return str(result[0])
    return f"Error: {error[0]}"


def _open_in_linear(task: Dict, workspace: str):
    key = task["identifier"]
    url = f"https://linear.app/{workspace}/issue/{key}" if workspace else f"https://linear.app/issue/{key}"
    webbrowser.open(url)


def _open_pr(prs: List[Dict]) -> str:
    """Open the first PR in browser. Returns error message if no PR."""
    if prs:
        webbrowser.open(prs[0]["url"])
        return ""
    return "No PR for this task"


def _refresh(linear, load_prs_fn, prs_ready):
    """Re-fetch tasks and kick off background PR load. Returns new task list."""
    tasks = linear.fetch_tasks()
    prs_ready.clear()
    threading.Thread(target=load_prs_fn, daemon=True).start()
    return tasks

# -- Entry point --------------------------------------------------------------


def main():
    # Handle `jora init <shell>`
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        shell = sys.argv[2] if len(sys.argv) > 2 else None
        if shell not in _SUPPORTED_SHELLS:
            print(f"Usage: jora init <{'|'.join(_SUPPORTED_SHELLS)}>", file=sys.stderr)
            sys.exit(1)
        print(_SHELL_INIT)
        return

    try:
        linear = LinearClient()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    term.init()

    active_key = _detect_active_task()

    try:
        tasks = linear.fetch_tasks()
    except Exception as e:
        term.cleanup()
        print(f"Error: {e}")
        sys.exit(1)

    # Load PR data in background
    prs_by_task = {}
    prs_ready = threading.Event()

    def load_prs():
        nonlocal prs_by_task
        prs_by_task = match_prs_to_tasks([t["identifier"] for t in tasks], fetch_prs())
        prs_ready.set()

    threading.Thread(target=load_prs, daemon=True).start()

    cursor = 0
    message = ""
    spin = 0
    # Main loop: render at 60fps, handle input
    while True:
        if tasks:
            cursor = max(0, min(cursor, len(tasks) - 1))

        loading = not prs_ready.is_set()

        if loading:
            spin += 1

        _draw(tasks, prs_by_task, cursor, active_key, message, spin_frame=spin // 4 if loading else -1)

        try:
            key = term.readkey()
        except KeyboardInterrupt:
            break

        if key is None:
            continue

        message = ""

        if key in ("q", "esc"):
            break
        if not tasks:
            continue

        if key == "up":
            cursor = max(0, cursor - 1)
        elif key == "down":
            cursor = min(len(tasks) - 1, cursor + 1)
        elif key in ("enter", "s"):
            path = _switch_to_task(tasks[cursor]["identifier"])
            if path.startswith("Error:"):
                message = path
            else:
                term.cleanup()
                Path("/tmp/jora_cd").write_text(path)
                return
        elif key == "o":
            _open_in_linear(tasks[cursor], linear.workspace)
        elif key == "p":
            message = _open_pr(prs_by_task.get(tasks[cursor]["identifier"], []))
        elif key == "r":
            try:
                tasks = _refresh(linear, load_prs, prs_ready)
                sorted_after_load = False
                spin = 0
            except Exception as e:
                message = f"Error: {e}"

    term.cleanup()
