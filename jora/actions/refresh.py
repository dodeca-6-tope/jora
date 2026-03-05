from jora.actions.action import Action


class Refresh(Action):
    key = "r"
    label = "refresh"

    def run(self, s, _data):
        s.menu.loading = True
        s.start_loading()
