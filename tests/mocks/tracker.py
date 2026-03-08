from jora.linear import Task, Tracker


class FakeTracker(Tracker):
    def __init__(self, tasks=None):
        self._tasks = [Task(**t) for t in tasks] if tasks else []

    def whoami(self):
        return "test-user"

    def fetch_tasks(self):
        return self._tasks
