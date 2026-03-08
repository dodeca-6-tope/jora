from jora.actions.action import Action
from jora.state import TaskItem


class PR(Action):
    key = "p"
    label = "PR"

    def run(self, s, row):
        if isinstance(row.data, TaskItem):
            s.open_task_pr(row.data.id)
        else:
            s.on_open_url(row.data.url)
