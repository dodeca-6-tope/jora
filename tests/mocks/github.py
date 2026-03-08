from jora.github import GitHub


class FakeGitHub(GitHub):
    def __init__(self, prs_by_task=None, review_prs=None):
        self._prs_by_task = prs_by_task or {}
        self._review_prs = review_prs or []

    def whoami(self):
        return "test-user"

    def warm(self):
        pass

    def is_branch_merged(self, slug, branch):
        return False

    def fetch_review_prs(self, slugs):
        return self._review_prs

    def fetch_task_prs(self, task_keys):
        return {k: v for k, v in self._prs_by_task.items() if k in task_keys}
