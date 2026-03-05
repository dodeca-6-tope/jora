import webbrowser
from jora.actions.action import Action


class PR(Action):
    key = "p"
    label = "PR"

    def run(self, s, row):
        if "identifier" in row.data:
            task_prs = s.prs_by_task.get(row.data["identifier"], [])
            if task_prs:
                webbrowser.open(task_prs[0]["url"])
            else:
                s.menu.message = "No PR for this task"
        else:
            webbrowser.open(row.data["url"])
