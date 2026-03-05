from jora.linear import Tracker


class FakeTracker(Tracker):
    def __init__(self, tasks=None):
        self._tasks = tasks or []

    def whoami(self):
        return "test-user"

    def fetch_tasks(self):
        return self._tasks
