from jora.actions.action import Action


class Kill(Action):
    key = "x"
    label = "kill"

    def run(self, s, row):
        s.kill_session(row.wt_key)
