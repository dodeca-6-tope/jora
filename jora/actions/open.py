import webbrowser
from jora.actions.action import Action


class Open(Action):
    key = "l"
    label = "linear"

    def run(self, _s, row):
        webbrowser.open(row.data["url"])
