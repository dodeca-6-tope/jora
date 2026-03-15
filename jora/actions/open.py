from jora.actions.action import Action


class Open(Action):
    key = "t"
    label = "task"

    def run(self, s, row):
        s.open_task_url(row.data.id)
