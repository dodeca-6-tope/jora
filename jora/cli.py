"""Interactive task picker UI."""

import sys
import threading
import webbrowser
from pathlib import Path

from jora.git import detect_active_task, switch_to_task
from jora.linear import LinearClient
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
from jora.term import Menu, Row

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


# -- Data preparation --------------------------------------------------------

_REVIEW_MARK = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}
_CI_MARK = {"SUCCESS": "ok", "FAILURE": "fail"}


def _build_rows(tasks, prs_by_task, active_key):
    rows = []
    for task in tasks:
        prs = prs_by_task.get(task["identifier"], [])
        pr = prs[0] if prs else None
        if pr:
            rv = _REVIEW_MARK.get(analyze_reviews(pr.get("reviews", [])), "neutral")
            ci = _CI_MARK.get(analyze_ci(pr.get("statusCheckRollup", [])), "neutral")
            marks = (rv, ci)
        else:
            marks = ()
        rows.append(Row(
            key=task["identifier"][:9],
            title=task.get("title", "No title"),
            marks=marks,
            active=task["identifier"].lower() == active_key,
        ))
    return rows


# -- Entry point --------------------------------------------------------------

def main():
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

    with Menu(loading=True) as menu:
        active_key = detect_active_task()

        tasks = []
        prs_by_task = {}
        tasks_ready = threading.Event()
        prs_ready = threading.Event()

        def load_tasks():
            nonlocal tasks
            try:
                tasks = linear.fetch_tasks()
            except Exception:
                pass
            tasks_ready.set()

        def load_prs():
            tasks_ready.wait()
            nonlocal prs_by_task
            prs_by_task = match_prs_to_tasks([t["identifier"] for t in tasks], fetch_prs())
            prs_ready.set()

        def start_loading():
            tasks_ready.clear()
            prs_ready.clear()
            threading.Thread(target=load_tasks, daemon=True).start()
            threading.Thread(target=load_prs, daemon=True).start()

        start_loading()

        while True:
            if tasks_ready.is_set():
                menu.rows = _build_rows(tasks, prs_by_task, active_key)
                menu.loading = not prs_ready.is_set()

            try:
                action = menu.tick()
            except KeyboardInterrupt:
                break

            if action is None:
                continue

            if action == "quit":
                break
            if action == "select":
                task_id = tasks[menu.selected]["identifier"]
                path = menu.run_blocking(
                    f"Switching to {task_id}",
                    lambda: switch_to_task(task_id),
                )
                if path.startswith("Error:"):
                    menu.message = path
                else:
                    Path("/tmp/jora_cd").write_text(path)
                    return
            elif action == "open":
                webbrowser.open(tasks[menu.selected]["url"])
            elif action == "pr":
                task_prs = prs_by_task.get(tasks[menu.selected]["identifier"], [])
                if task_prs:
                    webbrowser.open(task_prs[0]["url"])
                else:
                    menu.message = "No PR for this task"
            elif action == "refresh":
                menu.loading = True
                start_loading()
