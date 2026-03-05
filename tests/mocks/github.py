from jora.github import GitHub


class FakeGitHub(GitHub):
    def __init__(self, prs_by_task=None, review_prs=None):
        self._prs_by_task = prs_by_task or {}
        self._review_prs = review_prs or []

    def whoami(self): return "test-user"
    def warm(self): pass
    def repo_slug(self, repo_dir): return ""
    def is_pr_merged(self, repo_dir, branch): return False
    def fetch_review_prs(self, slugs): return self._review_prs

    def fetch_task_prs(self, task_keys):
        return {k: v for k, v in self._prs_by_task.items() if k in task_keys}

    def analyze_pr(self, pr):
        reviews = pr.get("reviews", [])
        checks = pr.get("statusCheckRollup", [])

        if not reviews:
            rv = "NO_REVIEWS"
        else:
            states = [r["state"] for r in reviews]
            if "APPROVED" in states:
                rv = "APPROVED"
            elif "CHANGES_REQUESTED" in states:
                rv = "CHANGES_REQUESTED"
            else:
                rv = "REVIEW_REQUIRED"

        if not checks:
            ci = "NONE"
        else:
            conclusions = [c.get("conclusion") for c in checks]
            if all(c == "SUCCESS" for c in conclusions):
                ci = "SUCCESS"
            elif "FAILURE" in conclusions:
                ci = "FAILURE"
            else:
                ci = "PENDING"

        return (rv, ci)
