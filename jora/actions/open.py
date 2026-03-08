from jora.actions.action import Action


class Open(Action):
    key = "l"
    label = "linear"

    def run(self, s, row):
        s.open_task_linear(row.data.id)
