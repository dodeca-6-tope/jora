from jora.actions.action import Action


class Kill(Action):
    key = "k"
    label = "kill"

    def enabled(self, s, row):
        return s.has_session(row.wt_key)

    def run(self, s, row):
        s.kill_session(row.wt_key)
