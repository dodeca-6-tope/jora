"""Interactive task picker UI."""

import argparse
import re
import sys
import threading
from dataclasses import dataclass, field
from typing import Dict, List

from jora.git import known_repos, list_worktrees, repo_path, add_repo, remove_repo
from jora import keychain, tmux
from jora.linear import LinearClient
from jora.github import GitHubClient
from jora.term import Menu, Row, Section
from jora.actions import (
    Select, Open, PR, Fix, Kill,
    Delete, Clean, Refresh, Quit,
)

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
      init) ;;
    esac
  fi
}
compdef _jora jora
"""


# -- Data preparation --------------------------------------------------------

_REVIEW_MARK = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}
_CI_MARK = {"SUCCESS": "ok", "FAILURE": "fail"}
_TICKET_RE = re.compile(r"[A-Z]+-\d+", re.IGNORECASE)

_SHARED = [Refresh(), Clean(), Quit()]
_TASK_ACTIONS = [Select(), Fix(), Kill(), Open(), PR(), *_SHARED]
_REVIEW_ACTIONS = [Select(), Kill(), Delete(), PR(), *_SHARED]


def _pr_ticket(pr):
    """Extract ticket ID from PR title/branch, or None."""
    for field in ("title", "headRefName"):
        m = _TICKET_RE.search(pr.get(field, ""))
        if m:
            return m.group(0).upper()
    return None


@dataclass
class State:
    linear: LinearClient
    github: GitHubClient
    menu: Menu
    tasks: List[Dict] = field(default_factory=list)
    prs_by_task: Dict[str, List[Dict]] = field(default_factory=dict)
    review_prs: List[Dict] = field(default_factory=list)
    review_titles: Dict[str, str] = field(default_factory=dict)
    _done: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def rebuild(self):
        with self._lock:
            worktrees = list_worktrees()
            sessions = tmux.list_sessions()
            self.menu.sections = self._build(worktrees, sessions)

    def _pr_marks(self, pr):
        if not pr:
            return ()
        rv = _REVIEW_MARK.get(self.github.analyze_reviews(pr.get("reviews", [])), "neutral")
        ci = _CI_MARK.get(self.github.analyze_ci(pr.get("statusCheckRollup", [])), "neutral")
        return (rv, ci)

    def _make_row(self, key, title, pr, wt_key, data, worktrees, sessions):
        return Row(
            key=key,
            title=title,
            wt_key=wt_key,
            marks=self._pr_marks(pr),
            worktree=wt_key in worktrees,
            session=tmux.session_name(wt_key) in sessions,
            data=data,
        )

    def _build(self, worktrees, sessions):
        sections = []
        tasks_by_id = {t["identifier"]: t for t in self.tasks}

        task_rows = []
        for task in self.tasks:
            pr = next(iter(self.prs_by_task.get(task["identifier"], [])), None)
            task_id = task["identifier"]
            task_rows.append(self._make_row(
                task_id[:9], task.get("title", "No title"), pr,
                task_id.lower(), task, worktrees, sessions,
            ))
        if task_rows:
            sections.append(Section(f"Tasks — {len(task_rows)}", task_rows, _TASK_ACTIONS))

        review_rows = []
        hidden = 0
        for pr in self.review_prs:
            ticket = _pr_ticket(pr)
            if not ticket:
                hidden += 1
                continue
            task = tasks_by_id.get(ticket)
            title = task["title"] if task else self.review_titles.get(ticket, "")
            review_rows.append(self._make_row(
                ticket[:9], title, pr,
                f"review-{pr['number']}", pr, worktrees, sessions,
            ))
        if review_rows:
            label = f"Review — {len(review_rows)}"
            if hidden:
                label += f" ({hidden} hidden)"
            sections.append(Section(label, review_rows, _REVIEW_ACTIONS))

        return sections

    def start_loading(self):
        self._done.clear()

        def load_tasks():
            try:
                self.tasks = self.linear.fetch_tasks()
            except Exception as e:
                self.menu.message = f"Failed to load tasks: {e}"
            self.rebuild()

        def load_prs():
            self.prs_by_task = self.github.match_prs_to_tasks(
                [t["identifier"] for t in self.tasks], self.github.fetch_prs(),
            )
            self.rebuild()

        def load_reviews():
            slugs = [s for name in known_repos() if (rp := repo_path(name)) and (s := self.github.repo_slug(str(rp)))]
            prs = self.github.fetch_review_prs(slugs)
            task_ids = {t["identifier"] for t in self.tasks}
            missing = {_pr_ticket(pr) for pr in prs if _pr_ticket(pr)} - task_ids
            titles = self.linear.fetch_issue_titles(list(missing)) if missing else {}
            self.review_prs = prs
            self.review_titles = titles
            self.rebuild()

        def go():
            threading.Thread(target=self.github.warm, daemon=True).start()
            load_tasks()
            t1 = threading.Thread(target=load_prs, daemon=True)
            t2 = threading.Thread(target=load_reviews, daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            self._done.set()

        threading.Thread(target=go, daemon=True).start()


# -- Entry point --------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(prog="jora", description="Linear task switcher with git worktrees")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="print shell init script (zsh)")
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
                print(f"Linear: authenticated as {name}")
            except Exception:
                print("Stored key is invalid — run: jora auth --reset")
        else:
            key = input("Linear API key (https://linear.app/settings/api): ").strip()
            if not key:
                print("No API key provided")
                sys.exit(1)
            try:
                name = LinearClient(key).whoami()
                keychain.store("linear", key)
                print(f"Linear: authenticated as {name}")
            except Exception as e:
                print(f"Invalid key: {e}", file=sys.stderr)
                sys.exit(1)
        try:
            print(f"GitHub: authenticated as {GitHubClient().whoami()}")
        except Exception:
            print("GitHub: not authenticated — run: gh auth login")
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
    github = GitHubClient()

    with Menu(loading=True) as menu:
        s = State(linear=linear, github=github, menu=menu)
        s.start_loading()

        while True:
            menu.loading = not s._done.is_set()

            try:
                key = menu.tick()
            except KeyboardInterrupt:
                break

            if key is None:
                continue

            sec, row = menu._at(menu._cursor)
            if not sec or not row:
                continue
            for action in sec.actions:
                if action.matches(key):
                    if action.run(s, row) == "exit":
                        return
                    break
