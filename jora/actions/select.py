from jora.actions.action import Action
from jora.actions.fix import _pick_repo
from jora.state import TaskItem


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
