from jora.actions.action import Action


class Kill(Action):
    key = "k"
    label = "kill"

    def enabled(self, s, row):
        return row.data.wt is not None and s.has_session(row.data.wt)

    def run(self, s, row):
        s.kill_session(row.data.wt)
