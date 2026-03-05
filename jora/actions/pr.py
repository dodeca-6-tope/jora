import webbrowser
from jora.actions.action import Action


class TaskPR(Action):
    key = "p"
    label = "PR"

    def run(self, s, task):
        task_prs = s.prs_by_task.get(task["identifier"], [])
        if task_prs:
            webbrowser.open(task_prs[0]["url"])
        else:
            s.menu.message = "No PR for this task"


class ReviewPR(Action):
    key = "p"
    label = "PR"

    def run(self, s, pr):
        webbrowser.open(pr["url"])
