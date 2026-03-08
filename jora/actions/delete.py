from jora.actions.action import Action


class Delete(Action):
    key = "d"
    label = "delete"

    def enabled(self, s, row):
        return row.data.wt is not None

    def run(self, s, row):
        s.delete_worktree(row.data.wt)
