from jora import tmux
from jora.actions.action import Action


def _kill_session(s, name):
    if not tmux.has_session(name):
        s.menu.message = "No session"
        return
    try:
        tmux.kill_session(name)
    except Exception as e:
        s.menu.message = f"Error: {e}"
    s.rebuild()


class TaskKill(Action):
    key = "x"
    label = "kill"

    def run(self, s, task):
        _kill_session(s, tmux.session_name(task["identifier"]))


class ReviewKill(Action):
    key = "x"
    label = "kill"

    def run(self, s, pr):
        _kill_session(s, tmux.session_name(f"review-{pr['number']}"))
