import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from jora import agent
from jora.git import Git
from jora.tmux import Tmux
from jora.linear import Tracker
from jora.github import GitHub
from jora.term import Menu, Row, Section
from jora.actions import Select, Open, PR, Fix, Kill, Delete, Clean, Refresh, Quit

_REVIEW_MARK = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}
_CI_MARK = {"SUCCESS": "ok", "FAILURE": "fail"}
_TICKET_RE = re.compile(r"[A-Z]+-\d+", re.IGNORECASE)

_SHARED = [Refresh(), Clean(), Quit()]
_TASK_ACTIONS = [Select(), Fix(), Kill(), Open(), PR(), *_SHARED]
_REVIEW_ACTIONS = [Select(), Kill(), Delete(), PR(), *_SHARED]


@dataclass
class State:
    git: Git
    tmux: Tmux
    linear: Tracker
    github: GitHub
    menu: Menu

    _tasks: List[Dict] = field(default_factory=list)
    _prs_by_task: Dict[str, List[Dict]] = field(default_factory=dict)
    _review_prs: List[Dict] = field(default_factory=list)
    _done: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def done(self) -> bool:
        return self._done.is_set()

    # -- Data loading --------------------------------------------------------

    def load(self):
        self._done.clear()

        def load_tasks():
            try:
                self._tasks = self.linear.fetch_tasks()
            except Exception as e:
                self.menu.message = f"Failed to load tasks: {e}"
            self.refresh()

        def load_prs():
            self._prs_by_task = self.github.fetch_task_prs(
                [t["identifier"] for t in self._tasks],
            )
            self.refresh()

        def load_reviews():
            slugs = [s for name in self.git.known_repos()
                     if (rp := self.git.repo_path(name)) and (s := self.github.repo_slug(str(rp)))]
            self._review_prs = self.github.fetch_review_prs(slugs)
            self.refresh()

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

    def refresh(self):
        with self._lock:
            worktrees = self.git.list_worktrees()
            sessions = self.tmux.list_sessions()
            self.menu.sections = self._build(worktrees, sessions)

    # -- Queries -------------------------------------------------------------

    def task_pr_url(self, task_id: str) -> Optional[str]:
        prs = self._prs_by_task.get(task_id, [])
        return prs[0]["url"] if prs else None

    def has_session(self, wt_key: str) -> bool:
        return self.tmux.has_session(self.tmux.session_name(wt_key))

    def has_worktree(self, wt_key: str) -> bool:
        return self.git.find_worktree(wt_key) is not None

    def worktree_path(self, wt_key: str) -> Optional[Path]:
        return self.git.find_worktree(wt_key)

    def repos(self) -> List[str]:
        return self.git.known_repos()

    # -- Operations ----------------------------------------------------------

    def open_task(self, task_id: str, repo: str = None):
        """Ensure worktree + session exist for a task."""
        wt = self.git.find_worktree(task_id)
        if not wt:
            rp = self.git.repo_path(repo)
            if not rp:
                raise ValueError(f"Repo {repo} not registered")
            wt = self.git.switch_to_task(task_id, rp)
        name = self.tmux.session_name(task_id)
        if not self.tmux.has_session(name):
            self.tmux.create_session(name, str(wt))
        self.refresh()

    def open_review(self, pr: Dict):
        """Ensure worktree + session exist for a review PR."""
        wt_key = f"review-{pr['number']}"
        wt = self.git.find_worktree(wt_key)
        if not wt:
            name = pr["repoSlug"].split("/")[-1]
            rp = self.git.repo_path(name)
            if not rp:
                raise ValueError(f"Repo {name} not registered")
            wt = self.git.checkout_pr(pr["number"], rp)
        name = self.tmux.session_name(wt_key)
        if not self.tmux.has_session(name):
            self.tmux.create_session(name, str(wt))
        self.refresh()

    def fix(self, task_id: str, repo: str = None):
        """Ensure worktree, create session, launch AI agent."""
        if self.has_session(task_id):
            self.menu.message = "Session already running — use ⏎ to attach"
            return
        wt = self.git.find_worktree(task_id)
        if wt and not self.git.is_worktree_clean(wt):
            self.menu.message = "Worktree has changes — use ⏎ to attach"
            return
        if not wt:
            rp = self.git.repo_path(repo)
            if not rp:
                raise ValueError(f"Repo {repo} not registered")
            wt = self.git.switch_to_task(task_id, rp)
        name = self.tmux.session_name(task_id)
        self.tmux.create_session(name, str(wt))
        self.tmux.send_keys(name, agent.command(task_id))
        self.refresh()

    def kill_session(self, wt_key: str):
        """Kill a tmux session."""
        name = self.tmux.session_name(wt_key)
        if not self.tmux.has_session(name):
            self.menu.message = "No session"
            return
        self.tmux.kill_session(name)
        self.menu.message = f"Killed session for {wt_key}"
        self.refresh()

    def delete_worktree(self, wt_key: str):
        """Kill session if running, remove worktree."""
        if not self.git.find_worktree(wt_key):
            self.menu.message = f"No worktree for {wt_key}"
            return
        name = self.tmux.session_name(wt_key)
        if self.tmux.has_session(name):
            self.tmux.kill_session(name)
        self.git.remove_worktree(wt_key)
        self.menu.message = f"Removed worktree for {wt_key}"
        self.refresh()

    def attach(self, wt_key: str):
        """Attach to a tmux session."""
        self.tmux.attach_session(self.tmux.session_name(wt_key))
        self.refresh()

    def clean(self) -> int:
        """Remove stale worktrees and their sessions. Returns count removed."""
        removed = self.git.clean_worktrees(self.github)
        for key in removed:
            name = self.tmux.session_name(key)
            if self.tmux.has_session(name):
                self.tmux.kill_session(name)
        n = len(removed)
        self.menu.message = f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
        if n:
            self.refresh()
        return n

    # -- View building -------------------------------------------------------

    def _pr_marks(self, pr):
        if not pr:
            return ()
        rv, ci = self.github.analyze_pr(pr)
        return (
            _REVIEW_MARK.get(rv, "neutral"),
            _CI_MARK.get(ci, "neutral"),
        )

    def _make_row(self, key, title, pr, wt_key, data, worktrees, sessions):
        return Row(
            key=key,
            title=title,
            wt_key=wt_key,
            marks=self._pr_marks(pr),
            worktree=wt_key in worktrees,
            session=self.tmux.session_name(wt_key) in sessions,
            data=data,
        )

    def _pr_ticket(self, pr):
        for f in ("title", "headRefName"):
            m = _TICKET_RE.search(pr.get(f, ""))
            if m:
                return m.group(0).upper()
        return None

    def _build(self, worktrees, sessions):
        sections = []
        tasks_by_id = {t["identifier"]: t for t in self._tasks}

        task_rows = []
        for task in self._tasks:
            pr = next(iter(self._prs_by_task.get(task["identifier"], [])), None)
            task_id = task["identifier"]
            task_rows.append(self._make_row(
                task_id[:9], task.get("title", "No title"), pr,
                task_id.lower(), task, worktrees, sessions,
            ))
        if task_rows:
            sections.append(Section(f"Tasks — {len(task_rows)}", task_rows, _TASK_ACTIONS))

        review_rows = []
        hidden = 0
        for pr in self._review_prs:
            ticket = self._pr_ticket(pr)
            if not ticket:
                hidden += 1
                continue
            task = tasks_by_id.get(ticket)
            if not task:
                hidden += 1
                continue
            review_rows.append(self._make_row(
                ticket[:9], task["title"], pr,
                f"review-{pr['number']}", pr, worktrees, sessions,
            ))
        if review_rows or hidden:
            label = f"Review — {len(review_rows)}"
            if hidden:
                label += f" ({hidden} hidden)"
            sections.append(Section(label, review_rows, _REVIEW_ACTIONS))

        return sections
