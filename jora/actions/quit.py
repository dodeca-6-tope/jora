from jora.actions.action import Action


class Quit(Exception):
    pass


class QuitAction(Action):
    key = "q"
    label = "quit"
    aliases = ("esc",)

    def run(self, s, _data):
        raise Quit
