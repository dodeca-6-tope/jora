from jora.actions.action import Action
from jora.actions.select import pick_repo


class Fix(Action):
    key = "f"
    label = "fix"

    def run(self, s, row):
        repo = None
        if not s.has_worktree(row.wt_key):
            repo = pick_repo(s, row.data["identifier"])
            if not repo:
                return
        try:
            s.menu.spin("Starting fix", lambda: s.fix(row.data["identifier"], repo))
        except Exception as e:
            s.menu.message = f"Error: {e}"
