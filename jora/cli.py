"""Interactive task picker UI."""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

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
from jora.linear import LinearClient
from jora.github import analyze_ci, analyze_reviews, fetch_prs, match_prs_to_tasks
from jora.term import Menu, Row, pick

# -- Shell init (jora init <shell>) ------------------------------------------

_SHELL_INIT = """\
jora() {
  command jora "$@"
  if [[ -f /tmp/jora_cd ]]; then
    cd "$(cat /tmp/jora_cd)"
    rm /tmp/jora_cd
  fi
}
_jora_completions() {
  local cmds="init add remove"
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=($(compgen -W "$cmds" -- "${COMP_WORDS[1]}"))
  elif [[ "${COMP_WORDS[1]}" == "remove" && $COMP_CWORD -eq 2 ]]; then
    local repos=$(ls ~/.jora/repos/ 2>/dev/null)
    COMPREPLY=($(compgen -W "$repos" -- "${COMP_WORDS[2]}"))
  elif [[ "${COMP_WORDS[1]}" == "add" && $COMP_CWORD -eq 2 ]]; then
    COMPREPLY=($(compgen -d -- "${COMP_WORDS[2]}"))
  fi
}
complete -F _jora_completions jora
"""
_SUPPORTED_SHELLS = ("zsh", "bash")


# -- Data preparation --------------------------------------------------------

_REVIEW_MARK = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}
_CI_MARK = {"SUCCESS": "ok", "FAILURE": "fail"}


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


# -- Repo picker -------------------------------------------------------------

def _pick_repo(task_id):
    """Show repo picker, return resolved repo Path or None if cancelled."""
    repos = known_repos()
    if not repos:
        return None

    idx = pick(f"Repo for {task_id}", repos)
    if idx is None:
        return None
    return repo_path(repos[idx])


# -- Entry point --------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(prog="jora", description="Linear task switcher with git worktrees")
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="print shell init script")
    init_p.add_argument("shell", choices=_SUPPORTED_SHELLS)

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

    try:
        linear = LinearClient()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    with Menu(loading=True) as menu:
        active_key = detect_active_task()

        tasks = []
        prs_by_task = {}
        worktrees = list_worktrees()
        prs_ready = threading.Event()

        def rebuild():
            nonlocal worktrees
            worktrees = list_worktrees()
            menu.rows = _build_rows(tasks, prs_by_task, active_key, worktrees)

        def load_tasks():
            nonlocal tasks
            try:
                tasks = linear.fetch_tasks()
            except Exception as e:
                menu.message = f"Failed to load tasks: {e}"
            rebuild()

        def load_prs():
            nonlocal prs_by_task
            prs_by_task = match_prs_to_tasks([t["identifier"] for t in tasks], fetch_prs())
            rebuild()
            prs_ready.set()

        def start_loading():
            prs_ready.clear()
            t_tasks = threading.Thread(target=load_tasks, daemon=True)
            t_prs = threading.Thread(target=load_prs, daemon=True)
            t_tasks.start()
            t_tasks.join()  # prs depend on tasks
            t_prs.start()

        threading.Thread(target=start_loading, daemon=True).start()

        while True:
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

                existing = find_worktree(task_id)
                if existing:
                    Path("/tmp/jora_cd").write_text(str(existing))
                    return

                repo = _pick_repo(task_id)
                if repo is None:
                    if not known_repos():
                        menu.message = "No repos. Run: jora add <path>"
                    continue

                try:
                    wt_path = menu.run_blocking(
                        f"Switching to {task_id}",
                        lambda: switch_to_task(task_id, repo),
                    )
                    Path("/tmp/jora_cd").write_text(str(wt_path))
                    return
                except Exception as e:
                    menu.message = f"Error: {e}"
            elif action == "open":
                webbrowser.open(tasks[menu.selected]["url"])
            elif action == "pr":
                task_prs = prs_by_task.get(tasks[menu.selected]["identifier"], [])
                if task_prs:
                    webbrowser.open(task_prs[0]["url"])
                else:
                    menu.message = "No PR for this task"
            elif action == "clean":
                try:
                    active_wt = find_worktree(active_key) if active_key else None
                    active_repo = active_wt.parent.name if active_wt else None
                    n = menu.run_blocking("Cleaning worktrees", clean_worktrees)
                    menu.message = f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
                    if n and active_wt and not active_wt.exists():
                        active_key = ""
                        rp = repo_path(active_repo) or Path.home()
                        Path("/tmp/jora_cd").write_text(str(rp))
                    if n:
                        rebuild()
                except Exception as e:
                    menu.message = f"Error: {e}"
            elif action == "refresh":
                menu.loading = True
                threading.Thread(target=start_loading, daemon=True).start()
