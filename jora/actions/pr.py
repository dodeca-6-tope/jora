from jora.actions.action import Action
from jora.state import TaskItem


class PR(Action):
    key = "p"
    label = "PR"

    def run(self, s, row):
        if isinstance(row.data, TaskItem):
            if row.data.pr_url:
                s.on_open_url(row.data.pr_url)
            else:
                s.on_alert("No PR for this task")
        else:
            item = row.data
            s.on_open_url(f"https://github.com/{item.repo_slug}/pull/{item.number}")
