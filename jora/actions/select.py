from jora.actions.action import Action
from jora.actions.fix import _pick_repo
from jora.state import TaskItem


class Select(Action):
    key = "⏎"
    label = "open"
    aliases = ("enter", "s")

    def run(self, s, row):
        if s.has_session(row.wt_key):
            s.attach(row.wt_key)
            return

        if isinstance(row.data, TaskItem):
            task_id = row.data.id
            repo = _pick_repo(s, task_id) if not s.has_worktree(row.wt_key) else None
            if not s.has_worktree(row.wt_key) and not repo:
                return
            s.run(lambda: s.open_task(task_id, repo), "Opening", then=lambda: s.attach(row.wt_key))
        else:
            item = row.data
            s.run(lambda: s.open_review(item.number, item.repo_slug, item.branch), "Opening", then=lambda: s.attach(row.wt_key))
