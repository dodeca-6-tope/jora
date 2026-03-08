from jora.actions.action import Action


class Clean(Action):
    key = "c"
    label = "clean"

    def run(self, s, _row):
        s.run(s.clean)
