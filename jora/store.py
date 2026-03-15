import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from jora.git import Git, Worktree
from jora.github import GitHub, PullRequest, analyze_pr
from jora.linear import Task, Tracker
from jora.state import ReviewItem, State, TaskItem
from jora.tmux import Tmux


@dataclass
class Store:
    git: Git
    tmux: Tmux
    linear: Tracker
    github: GitHub
    on_alert: Callable = lambda *a: None
    on_attach: Callable = lambda *a: None
    on_open_url: Callable = lambda *a: None
    on_defer: Callable = lambda *a: None
    on_change: Callable = lambda *a: None

    loading: int = 0
    loading_text: str = ""
    _tasks: list[Task] = field(default_factory=list)
    _prs_by_task: dict[str, list[PullRequest]] = field(default_factory=dict)
    _review_prs: list[PullRequest] = field(default_factory=list)
    _done: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_load: float = 0

    @property
    def done(self) -> bool:
        return self._done.is_set()

    # -- State snapshot ------------------------------------------------------

    @property
    def state(self) -> State:
        return State(
            tasks=tuple(self._build_task_items()),
            reviews=tuple(self._build_review_items()),
        )

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

    def fetch(self):
        """Fetch tasks, PRs, and reviews from APIs in parallel."""
        self._done.clear()

        def load_tasks():
            try:
                tasks = self.linear.fetch_tasks()
            except Exception as e:
                self.on_alert(f"Failed to load tasks: {e}")
                return
            with self._lock:
                self._tasks = tasks
            self.on_change()

        def load_prs():
            prs = self.github.fetch_task_prs(
                [t.identifier for t in self._tasks],
            )
            with self._lock:
                self._prs_by_task = prs
            self.on_change()

        def load_reviews():
            slugs = [
                s
                for name in self.git.known_repos()
                if (rp := self.git.repo_path(name))
                and (s := self.git.repo_slug(str(rp)))
            ]
            prs = self.github.fetch_review_prs(slugs)
            with self._lock:
                self._review_prs = prs
            self.on_change()

        threading.Thread(target=self.github.warm, daemon=True).start()
        # Reviews don't depend on tasks — start in parallel
        t_reviews = threading.Thread(target=load_reviews, daemon=True)
        t_reviews.start()
        # Tasks must complete before PRs (PRs match by task identifier)
        load_tasks()
        t_prs = threading.Thread(target=load_prs, daemon=True)
        t_prs.start()
        t_prs.join()
        t_reviews.join()
        self._done.set()
        self._last_load = time.time()

    def load(self):
        """Start initial data fetch in background."""
        self.run(self.fetch)

    _AUTO_RELOAD_INTERVAL = 10

    def maybe_reload(self, force=False):
        """Re-fetch if enough time has passed or force is set. Skips if already loading."""
        if not self._done.is_set():
            return
        if force or (
            self._last_load
            and time.time() - self._last_load >= self._AUTO_RELOAD_INTERVAL
        ):
            threading.Thread(target=self.fetch, daemon=True).start()

    def _session_name(self, wt: Worktree) -> str:
        return self.tmux.session_name(wt.repo, wt.key)

    # -- Queries -------------------------------------------------------------

    def task_pr_url(self, task_id: str) -> str | None:
        """Return the URL of the first PR matched to a task, or None."""
        prs = self._prs_by_task.get(task_id, [])
        return prs[0].url if prs else None

    def has_session(self, wt: Worktree) -> bool:
        """Check if a tmux session exists for the given worktree."""
        return self.tmux.has_session(self._session_name(wt))

    def repos(self) -> list[str]:
        """Return registered repo names sorted by worktree count."""
        return self.git.known_repos()

    def _pr_marks(self, pr: PullRequest):
        """Convert PR review/CI status to display marks (ok/fail/neutral)."""
        rv, ci = analyze_pr(pr)
        review = {"APPROVED": "ok", "CHANGES_REQUESTED": "fail"}.get(rv, "neutral")
        checks = {"SUCCESS": "ok", "FAILURE": "fail"}.get(ci, "neutral")
        return review, checks

    def _build_task_items(self) -> list[TaskItem]:
        """Return tasks enriched with worktree, session, and PR status."""
        with self._lock:
            tasks = list(self._tasks)
            prs_by_task = dict(self._prs_by_task)
        sessions = self.tmux.list_sessions()
        items = []
        for task in tasks:
            task_id = task.identifier
            wt = self.git.find_worktree_by_key(task_id.lower())
            pr = next(iter(prs_by_task.get(task_id, [])), None)
            review_status, ci_status = self._pr_marks(pr) if pr else ("", "")
            items.append(
                TaskItem(
                    id=task_id,
                    title=task.title,
                    url=task.url,
                    pr_url=pr.url if pr else "",
                    wt=wt,
                    review_status=review_status,
                    ci_status=ci_status,
                    session=wt is not None and self._session_name(wt) in sessions,
                )
            )
        return items

    def _build_review_items(self) -> list[ReviewItem]:
        """Return review PRs enriched with worktree and session status."""
        with self._lock:
            review_prs = list(self._review_prs)
        sessions = self.tmux.list_sessions()
        items = []
        for pr in review_prs:
            repo_name = pr.repo_slug.split("/")[-1]
            wt = Worktree(repo_name, f"review-{pr.number}")
            exists = self.git.find_worktree(wt) is not None
            review_status, ci_status = self._pr_marks(pr)
            items.append(
                ReviewItem(
                    id=wt.key,
                    number=pr.number,
                    title=pr.title,
                    repo_slug=pr.repo_slug,
                    branch=pr.head_ref,
                    wt=wt if exists else None,
                    review_status=review_status,
                    ci_status=ci_status,
                    session=exists and self._session_name(wt) in sessions,
                )
            )
        return items

    # -- Operations ----------------------------------------------------------

    def create_session(self, wt: Worktree):
        """Create a tmux session for an existing worktree."""
        name = self._session_name(wt)
        if not self.tmux.has_session(name):
            path = self.git.find_worktree(wt)
            self.tmux.create_session(name, str(path))
        self.on_change()

    def attach(self, wt: Worktree):
        """Attach to the tmux session for a worktree."""
        name = self._session_name(wt)
        self.on_attach(name)
        self.on_change()

    def create_task_worktree(self, task_id: str, repo: str = None) -> Worktree:
        """Ensure worktree exists for a task. Creates in repo if needed."""
        wt = self.git.find_worktree_by_key(task_id.lower())
        if not wt:
            rp = self.git.repo_path(repo)
            if not rp:
                raise ValueError(f"Repo {repo} not registered")
            wt = self.git.switch_to_task(task_id, rp)
        self.on_change()
        return wt

    def create_review_worktree(
        self, number: int, repo_slug: str, branch: str
    ) -> Worktree:
        """Ensure worktree exists for a review PR. Checks out branch if needed."""
        repo_name = repo_slug.split("/")[-1]
        wt = Worktree(repo_name, f"review-{number}")
        if not self.git.find_worktree(wt):
            rp = self.git.repo_path(repo_name)
            if not rp:
                raise ValueError(f"Repo {repo_name} not registered")
            self.git.checkout_pr(number, branch, rp)
        self.on_change()
        return wt

    def open_task_linear(self, task_id: str):
        """Open the Linear issue URL for a task."""
        task = next((t for t in self._tasks if t.identifier == task_id), None)
        if task:
            self.on_open_url(task.url)
        else:
            self.on_alert(f"Task {task_id} not found")

    def kill_session(self, wt: Worktree):
        """Kill the tmux session for a worktree."""
        name = self._session_name(wt)
        if not self.tmux.has_session(name):
            self.on_alert("No session")
            return
        self.tmux.kill_session(name)
        self.on_alert(f"Killed session for {wt.key}")
        self.on_change()

    def delete_worktree(self, wt: Worktree):
        """Remove a worktree and kill its session if running."""
        if not self.git.find_worktree(wt):
            self.on_alert(f"No worktree for {wt.key}")
            return
        name = self._session_name(wt)
        if self.tmux.has_session(name):
            self.tmux.kill_session(name)
        self.git.remove_worktree(wt)
        self.on_alert(f"Removed worktree for {wt.key}")
        self.on_change()

    def clean(self):
        """Remove stale worktrees (merged or no unique commits) and their sessions."""
        removed = self.git.clean_worktrees(self.github)
        for wt in removed:
            name = self._session_name(wt)
            if self.tmux.has_session(name):
                self.tmux.kill_session(name)
        n = len(removed)
        self.on_alert(
            f"Removed {n} worktree{'s' if n != 1 else ''}" if n else "Nothing to clean"
        )
        if n:
            self.on_change()
