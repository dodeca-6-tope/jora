from jora.actions.action import Action


class Clean(Action):
    key = "c"
    label = "clean"

    def run(self, s, _row):
        s.menu.spin_inline("Cleaning worktrees", s.clean)
