from jora.actions.action import Action


class Delete(Action):
    key = "d"
    label = "delete"

    def enabled(self, s, row):
        return s.has_worktree(row.wt_key)

    def run(self, s, row):
        s.menu.spin_inline(f"Removing {row.key}", lambda: s.delete_worktree(row.wt_key))
