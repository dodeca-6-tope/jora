from jora import tmux
from jora.actions.action import Action


class Kill(Action):
    key = "x"
    label = "kill"

    def run(self, s, row):
        name = tmux.session_name(row.wt_key)
        if not tmux.has_session(name):
            s.menu.message = "No session"
            return
        try:
            tmux.kill_session(name)
        except Exception as e:
            s.menu.message = f"Error: {e}"
        s.refresh()
