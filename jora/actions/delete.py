from jora.actions.action import Action


class Delete(Action):
    key = "d"
    label = "delete"

    def enabled(self, s, row):
        return s.has_worktree(row.wt_key)

    def run(self, s, row):
        s.delete_worktree(row.wt_key)
