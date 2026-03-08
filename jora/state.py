import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from jora import agent
from jora.git import Git
from jora.github import GitHub, PullRequest, analyze_pr
from jora.linear import Task, Tracker
from jora.tmux import Tmux


def _noop(*_args, **_kwargs):
    return None


@dataclass
class TaskItem:
    id: str
    title: str
    url: str
    review_status: str = ""
    ci_status: str = ""
    worktree: bool = False
    session: bool = False


@dataclass
class ReviewItem:
    id: str
    number: int
    title: str
    url: str
    repo_slug: str = ""
    branch: str = ""
    review_status: str = ""
    ci_status: str = ""
    worktree: bool = False
    session: bool = False


@dataclass
class State:
    git: Git
    tmux: Tmux
    linear: Tracker
    github: GitHub
    on_alert: Callable = _noop
    on_attach: Callable = _noop
    on_open_url: Callable = _noop
    on_defer: Callable = _noop
    on_change: Callable = _noop

    loading: int = 0
    loading_text: str = ""
    tasks: List[Task] = field(default_factory=list)
    prs_by_task: Dict[str, List[PullRequest]] = field(default_factory=dict)
    review_prs: List[PullRequest] = field(default_factory=list)
    _done: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_load: float = 0

    @property
    def done(self) -> bool:
        return self._done.is_set()

    # -- Background runner ---------------------------------------------------

    def run(self, fn: Callable, text: str = "", then: Callable = None):
        """Run fn in a background thread with loading indicator."""
        self.loading += 1
        self.loading_text = text

        def work():
            try:
                fn()
            except Exception as e:
                self.on_alert(f"Error: {e}")
                return
            finally:
                self.loading -= 1
                self.loading_text = ""
            if then:
                self.on_defer(then)

        threading.Thread(target=work, daemon=True).start()

    # -- Data loading --------------------------------------------------------

    def _fetch(self):
        """Fetch all data from APIs and refresh views."""
        self._done.clear()

        def load_tasks():
            try:
                self.tasks = self.linear.fetch_tasks()
            except Exception as e:
                self.on_alert(f"Failed to load tasks: {e}")
            self.on_change()

        def load_prs():
            prs = self.github.fetch_task_prs(
                [t.identifier for t in self.tasks],
            )
            with self._lock:
                self.prs_by_task = prs
            self.on_change()

        def load_reviews():
            slugs = [
                s
                for name in self.git.known_repos()
                if (rp := self.git.repo_path(name)) and (s := self.git.repo_slug(str(rp)))
            ]
            prs = self.github.fetch_review_prs(slugs)
            with self._lock:
                self.review_prs = prs
            self.on_change()

        threading.Thread(target=self.github.warm, daemon=True).start()
        t_reviews = threading.Thread(target=load_reviews, daemon=True)
        t_reviews.start()
        load_tasks()
        t_prs = threading.Thread(target=load_prs, daemon=True)
        t_prs.start()
        t_prs.join()
        t_reviews.join()
        self._done.set()
        self._last_load = time.time()

    def load(self):
        self.run(self._fetch)

    _AUTO_RELOAD_INTERVAL = 10

    def maybe_reload(self, force=False):
        if not self._done.is_set():
            return
        if force or (self._last_load and time.time() - self._last_load >= self._AUTO_RELOAD_INTERVAL):
            threading.Thread(target=self._fetch, daemon=True).start()

    # -- Queries -------------------------------------------------------------

    def task_pr_url(self, task_id: str) -> Optional[str]:
        prs = self.prs_by_task.get(task_id, [])
        return prs[0].url if prs else None

    def has_session(self, wt_key: str) -> bool:
        return self.tmux.has_session(self.tmux.session_name(wt_key))

    def has_worktree(self, wt_key: str) -> bool:
        return self.git.find_worktree(wt_key) is not None

    def worktree_path(self, wt_key: str) -> Optional[Path]:
        return self.git.find_worktree(wt_key)

    def repos(self) -> List[str]:
        return self.git.known_repos()

    def _pr_marks(self, pr: PullRequest):
        rv, ci = analyze_pr(pr)
        review = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}.get(rv, "neutral")
        checks = {"SUCCESS": "ok", "FAILURE": "fail"}.get(ci, "neutral")
        return review, checks

    def task_items(self) -> List[TaskItem]:
        worktrees = self.git.list_worktrees()
        sessions = self.tmux.list_sessions()
        items = []
        for task in self.tasks:
            task_id = task.identifier
            wt_key = task_id.lower()
            pr = next(iter(self.prs_by_task.get(task_id, [])), None)
            review_status, ci_status = self._pr_marks(pr) if pr else ("", "")
            items.append(
                TaskItem(
                    id=task_id,
                    title=task.title,
                    url=task.url,
                    review_status=review_status,
                    ci_status=ci_status,
                    worktree=wt_key in worktrees,
                    session=self.tmux.session_name(wt_key) in sessions,
                )
            )
        return items

    def review_items(self) -> List[ReviewItem]:
        worktrees = self.git.list_worktrees()
        sessions = self.tmux.list_sessions()
        items = []
        for pr in self.review_prs:
            wt_key = f"review-{pr.number}"
            review_status, ci_status = self._pr_marks(pr)
            items.append(
                ReviewItem(
                    id=wt_key,
                    number=pr.number,
                    title=pr.title,
                    url=pr.url,
                    repo_slug=pr.repo_slug,
                    branch=pr.head_ref,
                    review_status=review_status,
                    ci_status=ci_status,
                    worktree=wt_key in worktrees,
                    session=self.tmux.session_name(wt_key) in sessions,
                )
            )
        return items

    # -- Operations ----------------------------------------------------------

    def _ensure_session(self, wt_key: str):
        name = self.tmux.session_name(wt_key)
        if not self.tmux.has_session(name):
            wt = self.git.find_worktree(wt_key)
            self.tmux.create_session(name, str(wt))

    def attach(self, wt_key: str):
        """Attach to a tmux session."""
        name = self.tmux.session_name(wt_key)
        self.on_attach(name)
        self.on_change()

    def open_task(self, task_id: str, repo: str = None):
        """Ensure worktree + session exist for a task."""
        wt = self.git.find_worktree(task_id)
        if not wt:
            rp = self.git.repo_path(repo)
            if not rp:
                raise ValueError(f"Repo {repo} not registered")
            wt = self.git.switch_to_task(task_id, rp)
        self._ensure_session(task_id)
        self.on_change()

    def open_review(self, number: int, repo_slug: str, branch: str):
        """Ensure worktree + session exist for a review PR."""
        wt_key = f"review-{number}"
        wt = self.git.find_worktree(wt_key)
        if not wt:
            repo_name = repo_slug.split("/")[-1]
            rp = self.git.repo_path(repo_name)
            if not rp:
                raise ValueError(f"Repo {repo_name} not registered")
            wt = self.git.checkout_pr(number, branch, rp)
        self._ensure_session(wt_key)
        self.on_change()

    def open_task_pr(self, task_id: str):
        """Open the PR URL for a task."""
        url = self.task_pr_url(task_id)
        if url:
            self.on_open_url(url)
        else:
            self.on_alert("No PR for this task")

    def open_task_linear(self, task_id: str):
        """Open the Linear issue URL for a task."""
        task = next((t for t in self.tasks if t.identifier == task_id), None)
        if task:
            self.on_open_url(task.url)
        else:
            self.on_alert(f"Task {task_id} not found")

    def fix(self, task_id: str, repo: str = None):
        """Ensure worktree, create session, launch AI agent."""
        if self.has_session(task_id):
            self.on_alert("Session already running — use ⏎ to attach")
            return
        wt = self.git.find_worktree(task_id)
        if wt and not self.git.is_worktree_clean(wt):
            self.on_alert("Worktree has changes — use ⏎ to attach")
            return
        self.open_task(task_id, repo)
        name = self.tmux.session_name(task_id)
        self.tmux.send_keys(name, agent.command(f"Fix task {task_id}"))

    def kill_session(self, wt_key: str):
        """Kill a tmux session."""
        name = self.tmux.session_name(wt_key)
        if not self.tmux.has_session(name):
            self.on_alert("No session")
            return
        self.tmux.kill_session(name)
        self.on_alert(f"Killed session for {wt_key}")
        self.on_change()

    def delete_worktree(self, wt_key: str):
        """Kill session if running, remove worktree."""
        if not self.git.find_worktree(wt_key):
            self.on_alert(f"No worktree for {wt_key}")
            return
        name = self.tmux.session_name(wt_key)
        if self.tmux.has_session(name):
            self.tmux.kill_session(name)
        self.git.remove_worktree(wt_key)
        self.on_alert(f"Removed worktree for {wt_key}")
        self.on_change()

    def clean(self):
        """Remove stale worktrees and their sessions."""
        removed = self.git.clean_worktrees(self.github)
        for key in removed:
            name = self.tmux.session_name(key)
            if self.tmux.has_session(name):
                self.tmux.kill_session(name)
        n = len(removed)
        self.on_alert(f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean")
        if n:
            self.on_change()
