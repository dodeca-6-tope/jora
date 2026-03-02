import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Dict, List

from jora.exceptions import ClientException
from jora.git import switch_to_task
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
from jora.linear import LinearClient
import jora.term as term

DIM = "\033[90m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"
SPINNER = r"-\|/"

# Visible chars before title: "  > ● ■ LTXD-408  "
_PREFIX = 18


def _indicators(prs: List[Dict]) -> str:
    if not prs:
        return "   "
    review = analyze_reviews(prs[0].get("reviews", []))
    ci = analyze_ci(prs[0].get("statusCheckRollup", []))
    rv = {"APPROVED": f"{GREEN}●{RESET}", "CHANGES_REQUESTED": f"{RED}●{RESET}"}.get(review, f"{DIM}○{RESET}")
    ck = {"SUCCESS": f"{GREEN}■{RESET}", "FAILURE": f"{RED}■{RESET}", "PENDING": f"{YELLOW}■{RESET}"}.get(ci, f"{DIM}□{RESET}")
    return f"{rv} {ck}"


def _format_task(task: Dict, prs: List[Dict], selected: bool, active: bool) -> str:
    ident_raw = task['identifier'][:9]
    ident = f"{CYAN}{ident_raw:<9}{RESET}" if active else f"{DIM}{ident_raw:<9}{RESET}"
    title = task.get("title", "No title")
    avail = os.get_terminal_size().columns - _PREFIX
    if avail > 3 and len(title) > avail:
        title = title[: avail - 3] + "..."
    cur = f"{CYAN}>{RESET}" if selected else " "
    return f"  {cur} {_indicators(prs)} {ident} {title}"


def _pr_sort_key(task: Dict, prs_by_task: Dict) -> int:
    prs = prs_by_task.get(task["identifier"])
    if not prs:
        return 4
    status = analyze_reviews(prs[0].get("reviews", []))
    return {"APPROVED": 0, "CHANGES_REQUESTED": 1, "REVIEW_REQUIRED": 1}.get(status, 2)


def _draw(tasks, prs_by_task, cursor, active_key="", message="", spin_frame=-1):
    term.clear()
    spinner = f" {DIM}{SPINNER[spin_frame % len(SPINNER)]}{RESET}" if spin_frame >= 0 else ""
    print(f"{BOLD}Jora{RESET} — {len(tasks)} tasks{spinner}\n")
    for i, task in enumerate(tasks):
        active = task["identifier"].lower() == active_key
        print(_format_task(task, prs_by_task.get(task["identifier"], []), i == cursor, active))
    print()
    if message:
        print(f"  {message}\n")
    print(f"  {DIM}enter switch  o open  p PR  r refresh  q quit{RESET}")


def main():
    try:
        linear = LinearClient()
    except ClientException as e:
        print(f"Error: {e}")
        sys.exit(1)

    term.init()

    # Detect active task from cwd (if in a worktree)
    cwd = Path.cwd()
    active_key = cwd.name if ".worktrees" in cwd.parts else ""

    try:
        tasks = linear.fetch_tasks()
    except ClientException as e:
        term.cleanup()
        print(f"Error: {e}")
        sys.exit(1)

    prs_by_task = {}
    prs_ready = threading.Event()

    def load_prs():
        nonlocal prs_by_task
        all_prs = fetch_prs()
        prs_by_task = match_prs_to_tasks([t["identifier"] for t in tasks], all_prs)
        prs_ready.set()

    threading.Thread(target=load_prs, daemon=True).start()

    cursor = 0
    message = ""
    spin = 0
    sorted_after_load = False

    while True:
        if tasks:
            cursor = max(0, min(cursor, len(tasks) - 1))

        loading = not prs_ready.is_set()

        if not loading and not sorted_after_load:
            selected_id = tasks[cursor]["identifier"] if tasks else None
            tasks.sort(key=lambda t: _pr_sort_key(t, prs_by_task))
            cursor = next((i for i, t in enumerate(tasks) if t["identifier"] == selected_id), 0) if selected_id else 0
            sorted_after_load = True

        if loading:
            spin += 1

        _draw(tasks, prs_by_task, cursor, active_key, message, spin_frame=spin // 4 if loading else -1)
        message = ""

        try:
            key = term.readkey()
        except KeyboardInterrupt:
            break

        if key is None:
            continue
        if key in ("q", "esc"):
            break
        if not tasks:
            continue

        if key == "up":
            cursor = max(0, cursor - 1)
        elif key == "down":
            cursor = min(len(tasks) - 1, cursor + 1)
        elif key in ("enter", "s"):
            task_id = tasks[cursor]["identifier"]
            result = [None]
            error = [None]

            def do_switch():
                try:
                    result[0] = switch_to_task(task_id)
                except subprocess.CalledProcessError as e:
                    error[0] = str(e)

            t = threading.Thread(target=do_switch, daemon=True)
            t.start()
            s = 0
            while t.is_alive():
                s += 1
                _draw(tasks, prs_by_task, cursor, active_key,
                      f"Switching to {task_id}... {SPINNER[s // 4 % len(SPINNER)]}")
                t.join(timeout=1 / 60)

            if result[0]:
                term.cleanup()
                Path("/tmp/jora_cd").write_text(str(result[0]))
                return
            else:
                message = f"Error: {error[0]}"
        elif key == "o":
            tk = tasks[cursor]["identifier"]
            ws = linear.workspace
            webbrowser.open(f"https://linear.app/{ws}/issue/{tk}" if ws else f"https://linear.app/issue/{tk}")
        elif key == "p":
            prs = prs_by_task.get(tasks[cursor]["identifier"], [])
            if prs:
                webbrowser.open(prs[0]["url"])
            else:
                message = "No PR for this task"
        elif key == "r":
            _draw(tasks, prs_by_task, cursor, active_key, "Refreshing...")
            try:
                tasks = linear.fetch_tasks()
                prs_by_task = {}
                prs_ready.clear()
                sorted_after_load = False
                spin = 0
                threading.Thread(target=load_prs, daemon=True).start()
            except ClientException as e:
                message = f"Error: {e}"

    term.cleanup()
