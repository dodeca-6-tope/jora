from jora import tmux
from jora.git import checkout_pr, find_worktree, known_repos, repo_path, switch_to_task
from jora.actions.action import Action
from jora.term import pick, suspend, resume


def _ensure_task_worktree(s, task_id):
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


def _ensure_review_worktree(s, pr):
    wt_key = f"review-{pr['number']}"
    wt = find_worktree(wt_key)
    if wt:
        return wt
    name = pr["repoSlug"].split("/")[-1]
    rp = repo_path(name)
    if not rp:
        s.menu.message = f"Repo {name} not registered"
        return None
    try:
        return s.menu.run_blocking(
            f"Checking out #{pr['number']}",
            lambda: checkout_pr(pr["number"], rp),
        )
    except Exception as e:
        s.menu.message = f"Error: {e}"
        return None


def _open_session(s, name, wt):
    if not tmux.has_session(name):
        if not wt:
            return
        try:
            tmux.create_session(name, str(wt))
        except Exception as e:
            s.menu.message = f"Error: {e}"
            return
    suspend()
    tmux.attach_session(name)
    resume()
    s.rebuild()


class TaskSelect(Action):
    key = "⏎"
    label = "open"
    aliases = ("enter", "s")

    def run(self, s, task):
        task_id = task["identifier"]
        name = tmux.session_name(task_id)
        wt = find_worktree(task_id) if tmux.has_session(name) else _ensure_task_worktree(s, task_id)
        _open_session(s, name, wt)


class ReviewSelect(Action):
    key = "⏎"
    label = "open"
    aliases = ("enter", "s")

    def run(self, s, pr):
        name = tmux.session_name(f"review-{pr['number']}")
        wt = find_worktree(f"review-{pr['number']}") if tmux.has_session(name) else _ensure_review_worktree(s, pr)
        _open_session(s, name, wt)
