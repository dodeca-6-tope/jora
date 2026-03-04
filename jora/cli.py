"""Interactive task picker UI."""

import argparse
import sys
import threading
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from jora.git import (
    add_repo,
    clean_worktrees,
    detect_active_task,
    find_worktree,
    known_repos,
    list_worktrees,
    remove_repo,
    repo_path,
    switch_to_task,
)
from jora import keychain
from jora.linear import LinearClient
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
from jora.term import Menu, Row, pick

_CD_FILE = Path.home() / ".jora" / "cd"

# -- Shell init (jora init <shell>) ------------------------------------------

_SHELL_INIT = """\
jora() {
  command jora "$@"
  if [[ -f ~/.jora/cd ]]; then
    cd "$(cat ~/.jora/cd)"
    rm -f ~/.jora/cd
  fi
}
_jora() {
  if (( CURRENT == 2 )); then
    compadd auth init add remove
  elif (( CURRENT == 3 )); then
    case $words[2] in
      remove) compadd $(ls ~/.jora/repos/ 2>/dev/null) ;;
      add) _directories ;;
      init) compadd zsh ;;
    esac
  fi
}
compdef _jora jora
"""


# -- Data preparation --------------------------------------------------------

_REVIEW_MARK = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}
_CI_MARK = {"SUCCESS": "ok", "FAILURE": "fail"}


@dataclass
class State:
    linear: LinearClient
    menu: Menu
    tasks: List[Dict] = field(default_factory=list)
    prs_by_task: Dict[str, List[Dict]] = field(default_factory=dict)
    worktrees: Dict[str, Path] = field(default_factory=dict)
    active_key: str = ""
    prs_ready: threading.Event = field(default_factory=threading.Event)

    def rebuild(self):
        self.worktrees = list_worktrees()
        self.menu.rows = _build_rows(self.tasks, self.prs_by_task, self.active_key, self.worktrees)

    def start_loading(self):
        self.prs_ready.clear()

        def load_tasks():
            try:
                self.tasks = self.linear.fetch_tasks()
            except Exception as e:
                self.menu.message = f"Failed to load tasks: {e}"
            self.rebuild()

        def load_prs():
            self.prs_by_task = match_prs_to_tasks(
                [t["identifier"] for t in self.tasks], fetch_prs(),
            )
            self.rebuild()
            self.prs_ready.set()

        def go():
            t = threading.Thread(target=load_tasks, daemon=True)
            t.start()
            t.join()  # prs depend on tasks
            threading.Thread(target=load_prs, daemon=True).start()

        threading.Thread(target=go, daemon=True).start()


def _build_rows(tasks, prs_by_task, active_key, worktrees):
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
        task_lower = task["identifier"].lower()
        rows.append(Row(
            key=task["identifier"][:9],
            title=task.get("title", "No title"),
            marks=marks,
            active=task_lower == active_key,
            worktree=task_lower in worktrees,
        ))
    return rows


# -- Action handlers ---------------------------------------------------------
# Each returns "continue", "break", or "return".

def _cd_to(path):
    _CD_FILE.write_text(str(path))
    return "return"


def _on_select(s):
    task_id = s.tasks[s.menu.selected]["identifier"]

    existing = find_worktree(task_id)
    if existing:
        return _cd_to(existing)

    repos = known_repos()
    if not repos:
        s.menu.message = "No repos. Run: jora add <path>"
        return "continue"

    idx = pick(f"Repo for {task_id}", repos)
    if idx is None:
        return "continue"
    repo = repo_path(repos[idx])

    try:
        wt_path = s.menu.run_blocking(
            f"Switching to {task_id}",
            lambda: switch_to_task(task_id, repo),
        )
        return _cd_to(wt_path)
    except Exception as e:
        s.menu.message = f"Error: {e}"
        return "continue"


def _on_open(s):
    webbrowser.open(s.tasks[s.menu.selected]["url"])
    return "continue"


def _on_pr(s):
    task_prs = s.prs_by_task.get(s.tasks[s.menu.selected]["identifier"], [])
    if task_prs:
        webbrowser.open(task_prs[0]["url"])
    else:
        s.menu.message = "No PR for this task"
    return "continue"


def _on_clean(s):
    try:
        active_wt = find_worktree(s.active_key) if s.active_key else None
        active_repo = active_wt.parent.name if active_wt else None
        n = s.menu.run_blocking("Cleaning worktrees", clean_worktrees)
        s.menu.message = f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
        if n and active_wt and not active_wt.exists():
            s.active_key = ""
            rp = repo_path(active_repo) or Path.home()
            _CD_FILE.write_text(str(rp))
        if n:
            s.rebuild()
    except Exception as e:
        s.menu.message = f"Error: {e}"
    return "continue"


def _on_refresh(s):
    s.menu.loading = True
    s.start_loading()
    return "continue"


_ACTIONS = {
    "select": _on_select,
    "open": _on_open,
    "pr": _on_pr,
    "clean": _on_clean,
    "refresh": _on_refresh,
}


# -- Entry point --------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(prog="jora", description="Linear task switcher with git worktrees")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="print shell init script")
    auth_p = sub.add_parser("auth", help="set Linear API key")
    auth_p.add_argument("--reset", action="store_true", help="replace existing key")

    add_p = sub.add_parser("add", help="register a repo")
    add_p.add_argument("target", help="local path (symlink) or git URL (clone)")

    rm_p = sub.add_parser("remove", help="unregister a repo")
    rm_p.add_argument("name", help="repo name from ~/.jora/repos/")

    return parser.parse_args()


def main():
    args = _parse_args()

    if args.command == "init":
        print(_SHELL_INIT)
        return

    if args.command == "auth":
        existing = keychain.get("linear")
        if existing and not args.reset:
            try:
                name = LinearClient(existing).whoami()
                print(f"Authenticated as {name}")
            except Exception:
                print("Stored key is invalid — run: jora auth --reset")
            return
        key = input("Linear API key (https://linear.app/settings/api): ").strip()
        if not key:
            print("No API key provided")
            sys.exit(1)
        try:
            name = LinearClient(key).whoami()
            keychain.set("linear", key)
            print(f"Authenticated as {name}")
        except Exception as e:
            print(f"Invalid key: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "add":
        try:
            name = add_repo(args.target)
            print(f"Added {name}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "remove":
        try:
            remove_repo(args.name)
            print(f"Removed {args.name}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    api_key = keychain.get("linear")
    if not api_key:
        print("No API key — run: jora auth")
        sys.exit(1)
    linear = LinearClient(api_key)

    with Menu(loading=True) as menu:
        s = State(linear=linear, menu=menu, active_key=detect_active_task(),
                  worktrees=list_worktrees())
        s.start_loading()

        while True:
            menu.loading = not s.prs_ready.is_set()

            try:
                action = menu.tick()
            except KeyboardInterrupt:
                break

            if action is None:
                continue
            if action == "quit":
                break

            handler = _ACTIONS.get(action)
            if handler:
                result = handler(s)
                if result == "return":
                    return
                if result == "break":
                    break
