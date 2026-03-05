import webbrowser
from jora.actions.action import Action


class TaskOpen(Action):
    key = "o"
    label = "linear"

    def run(self, s, task):
        webbrowser.open(task["url"])
