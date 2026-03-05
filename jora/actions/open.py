import webbrowser
from jora.actions.action import Action


class Open(Action):
    key = "o"
    label = "linear"

    def run(self, _s, row):
        webbrowser.open(row.data["url"])
