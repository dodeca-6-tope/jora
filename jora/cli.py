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
    find_worktree,
    is_worktree_clean,
    known_repos,
    list_worktrees,
    remove_repo,
    repo_path,
    switch_to_task,
)
from jora import agent, keychain, tmux
from jora.linear import LinearClient
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
from jora.term import Menu, Row, pick, suspend, resume

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
    sessions: set = field(default_factory=set)
    prs_ready: threading.Event = field(default_factory=threading.Event)

    def rebuild(self):
        self.worktrees = list_worktrees()
        self.sessions = tmux.list_sessions()
        self.menu.rows = _build_rows(self.tasks, self.prs_by_task, self.worktrees, self.sessions)

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


def _build_rows(tasks, prs_by_task, worktrees, sessions):
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
            worktree=task_lower in worktrees,
            session=tmux.session_name(task_lower) in sessions,
        ))
    return rows


# -- Action handlers ---------------------------------------------------------
# Each returns "continue", "break", or "return".

def _ensure_worktree(s, task_id):
    """Return worktree path, creating if needed. None on failure/cancel."""
    wt = find_worktree(task_id)
    if wt:
        return wt

    repos = known_repos()
    if not repos:
        s.menu.message = "No repos. Run: jora add <path>"
        return None

    idx = pick(f"Repo for {task_id}", repos)
    if idx is None:
        return None
    repo = repo_path(repos[idx])

    try:
        return s.menu.run_blocking(
            f"Creating worktree for {task_id}",
            lambda: switch_to_task(task_id, repo),
        )
    except Exception as e:
        s.menu.message = f"Error: {e}"
        return None


def _on_select(s):
    task_id = s.tasks[s.menu.selected]["identifier"]
    name = tmux.session_name(task_id)

    if not tmux.has_session(name):
        wt = _ensure_worktree(s, task_id)
        if not wt:
            return "continue"
        try:
            tmux.create_session(name, str(wt))
        except Exception as e:
            s.menu.message = f"Error creating session: {e}"
            return "continue"

    suspend()
    tmux.attach_session(name)
    resume()
    s.rebuild()
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
        before = set(s.worktrees.keys())
        n = s.menu.run_blocking("Cleaning worktrees", clean_worktrees)
        after = set(list_worktrees().keys())
        for removed_key in before - after:
            name = tmux.session_name(removed_key)
            if tmux.has_session(name):
                tmux.kill_session(name)
        s.menu.message = f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
        if n:
            s.rebuild()
    except Exception as e:
        s.menu.message = f"Error: {e}"
    return "continue"


def _on_refresh(s):
    s.menu.loading = True
    s.start_loading()
    return "continue"


def _on_fix(s):
    task = s.tasks[s.menu.selected]
    task_id = task["identifier"]
    name = tmux.session_name(task_id)

    if tmux.has_session(name):
        s.menu.message = "Session already running — use ⏎ to attach"
        return "continue"

    wt = find_worktree(task_id)
    if wt and not is_worktree_clean(wt):
        s.menu.message = "Worktree has changes — use ⏎ to attach"
        return "continue"

    if not wt:
        wt = _ensure_worktree(s, task_id)
        if not wt:
            return "continue"

    try:
        tmux.create_session(name, str(wt))
    except Exception as e:
        s.menu.message = f"Error creating session: {e}"
        return "continue"

    tmux.send_keys(name, agent.command(task_id))

    s.rebuild()
    return "continue"


def _on_kill(s):
    task_id = s.tasks[s.menu.selected]["identifier"]
    name = tmux.session_name(task_id)
    if not tmux.has_session(name):
        s.menu.message = "No session for this task"
        return "continue"
    try:
        tmux.kill_session(name)
    except Exception as e:
        s.menu.message = f"Error killing session: {e}"
    s.rebuild()
    return "continue"


_ACTIONS = {
    "select": _on_select,
    "open": _on_open,
    "pr": _on_pr,
    "fix": _on_fix,
    "kill": _on_kill,
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
        s = State(linear=linear, menu=menu,
                  worktrees=list_worktrees(), sessions=tmux.list_sessions())
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
