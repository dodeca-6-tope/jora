from jora.actions.action import Action
from jora.state import TaskItem


def _pick_repo(s, task_id):
    from jora.app import pick

    repos = s.repos()
    if not repos:
        s.on_alert("No repos. Run: jora add <path>")
        return None
    idx = pick(f"Repo for {task_id}", repos)
    return repos[idx] if idx is not None else None


class Select(Action):
    key = "⏎"
    label = "open"
    aliases = ("enter", "s")

    def run(self, s, row):
        item = row.data
        if item.wt and s.has_session(item.wt):
            s.attach(item.wt)
            return

        if isinstance(item, TaskItem):
            task_id = item.id
            repo = _pick_repo(s, task_id) if not item.wt else None
            if not item.wt and not repo:
                return

            def open_and_attach():
                wt = s.create_task_worktree(task_id, repo)
                s.create_session(wt)
                s.on_defer(lambda: s.attach(wt))

            s.run(open_and_attach, "Opening")
        else:

            def open_and_attach():
                wt = s.create_review_worktree(item.number, item.repo_slug, item.branch)
                s.create_session(wt)
                s.on_defer(lambda: s.attach(wt))

            s.run(open_and_attach, "Opening")
