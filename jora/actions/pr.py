import webbrowser
from jora.actions.action import Action


class PR(Action):
    key = "p"
    label = "PR"

    def run(self, s, row):
        if "identifier" in row.data:
            url = s.task_pr_url(row.data["identifier"])
            if url:
                webbrowser.open(url)
            else:
                s.menu.message = "No PR for this task"
        else:
            webbrowser.open(row.data["url"])
