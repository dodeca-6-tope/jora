from jora.actions.action import Action


class Quit(Action):
    key = "q"
    label = "quit"
    aliases = ("esc",)

    def run(self, _s, _row):
        return "exit"
