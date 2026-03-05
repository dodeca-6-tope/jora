import threading

from jora.actions.action import Action


class Clean(Action):
    key = "c"
    label = "clean"

    def run(self, s, _row):
        threading.Thread(target=s.clean, daemon=True).start()
