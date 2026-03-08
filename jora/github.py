import contextlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests


@dataclass
class CheckStatus:
    """A CI check result (CheckRun conclusion or StatusContext state)."""

    conclusion: str  # SUCCESS, FAILURE, NEUTRAL, PENDING, etc.


@dataclass
class PullRequestReview:
    """A review on a pull request."""

    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED, PENDING
    author_login: str


@dataclass
class PullRequest:
    number: int
    title: str
    url: str
    body: str
    head_ref: str
    author_login: str
    repo_slug: str
    reviews: list[PullRequestReview] = field(default_factory=list)
    checks: list[CheckStatus] = field(default_factory=list)


_PR_FIELDS = """
  ... on PullRequest {
    number
    title
    url
    body
    headRefName
    author { login }
    repository { nameWithOwner }
    reviews(last: 20) {
      nodes { state author { login } }
    }
    commits(last: 1) {
      nodes {
        commit {
          statusCheckRollup {
            contexts(first: 50) {
              nodes {
                ... on CheckRun { conclusion }
                ... on StatusContext { state }
              }
            }
          }
        }
      }
    }
  }
"""

_AUTHORED_QUERY = f"""
{{
  search(query: "is:pr is:open author:@me", type: ISSUE, first: 100) {{
    nodes {{ {_PR_FIELDS} }}
  }}
}}
"""

_REVIEW_QUERY = f"""
query($q: String!) {{
  search(query: $q, type: ISSUE, first: 100) {{
    nodes {{ {_PR_FIELDS} }}
  }}
}}
"""


# -- Analysis ---------------------------------------------------------------


def analyze_pr(pr: PullRequest) -> tuple:
    """Return (review_status, ci_status) for a PR."""
    return (_review_status(pr.reviews), _ci_status(pr.checks))


def _ci_status(checks: list[CheckStatus]) -> str:
    if not checks:
        return "NONE"
    if all(c.conclusion == "SUCCESS" for c in checks):
        return "SUCCESS"
    if any(c.conclusion == "FAILURE" for c in checks):
        return "FAILURE"
    return "PENDING"


def _review_status(reviews: list[PullRequestReview]) -> str:
    if not reviews:
        return "NO_REVIEWS"
    latest_by_reviewer = {}
    for r in reviews:
        if r.author_login:
            latest_by_reviewer[r.author_login] = r
    latest = list(latest_by_reviewer.values())
    if any(r.state == "CHANGES_REQUESTED" for r in latest):
        return "CHANGES_REQUESTED"
    if any(r.state == "APPROVED" for r in latest):
        return "APPROVED"
    return "REVIEW_REQUIRED"


def _latest_review_by(pr: PullRequest, login: str) -> str:
    for r in reversed(pr.reviews):
        if r.author_login == login:
            return r.state
    return ""


# -- Normalization ----------------------------------------------------------


def _match_prs_to_tasks(
    task_keys: list[str], all_prs: list[PullRequest]
) -> dict[str, list[PullRequest]]:
    result = {}
    for key in task_keys:
        pattern = re.compile(re.escape(key) + r"(?!\w)", re.IGNORECASE)
        matches = [
            pr
            for pr in all_prs
            if pattern.search(pr.title)
            or pattern.search(pr.head_ref)
            or pattern.search(pr.body)
        ]
        matches.sort(key=lambda pr: 0 if pattern.search(pr.head_ref) else 1)
        if matches:
            result[key] = matches
    return result


def _parse_pr(node: dict) -> PullRequest:
    reviews = [
        PullRequestReview(
            state=r["state"],
            author_login=(r.get("author") or {}).get("login", ""),
        )
        for r in (node.get("reviews", {}).get("nodes", []) or [])
    ]
    commits = node.get("commits", {}).get("nodes", []) or []
    checks = []
    if commits:
        rollup = commits[0].get("commit", {}).get("statusCheckRollup") or {}
        checks = [
            CheckStatus(conclusion=ctx.get("conclusion") or ctx.get("state") or "")
            for ctx in (rollup.get("contexts", {}).get("nodes", []) or [])
        ]
    return PullRequest(
        number=node["number"],
        title=node.get("title", ""),
        url=node.get("url", ""),
        body=node.get("body", ""),
        head_ref=node.get("headRefName", ""),
        author_login=(node.get("author") or {}).get("login", ""),
        repo_slug=(node.get("repository") or {}).get("nameWithOwner", ""),
        reviews=reviews,
        checks=checks,
    )


# -- Abstract + Client ------------------------------------------------------


class GitHub(ABC):
    """GitHub API backend for PRs, reviews, and CI status."""

    @abstractmethod
    def whoami(self) -> str: ...

    @abstractmethod
    def warm(self): ...

    @abstractmethod
    def fetch_task_prs(self, task_keys: list[str]) -> dict[str, list[PullRequest]]: ...

    @abstractmethod
    def fetch_review_prs(self, repo_slugs: list[str]) -> list[PullRequest]: ...

    @abstractmethod
    def is_branch_merged(self, slug: str, branch: str) -> bool: ...


class GitHubClient(GitHub):
    _API = "https://api.github.com"

    def __init__(self, token: str):
        self._token = token
        self._login = None
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def whoami(self) -> str:
        if self._login is not None:
            return self._login
        r = self._session.get(f"{self._API}/user", timeout=10)
        if r.status_code != 200:
            raise RuntimeError("GitHub auth failed — run: jora auth --reset")
        self._login = r.json()["login"]
        return self._login

    def warm(self):
        with contextlib.suppress(Exception):
            self.whoami()

    def fetch_task_prs(self, task_keys: list[str]) -> dict[str, list[PullRequest]]:
        try:
            r = self._graphql(_AUTHORED_QUERY)
            nodes = r.get("data", {}).get("search", {}).get("nodes", [])
            all_prs = [_parse_pr(n) for n in nodes if n]
        except (requests.RequestException, KeyError):
            all_prs = []
        return _match_prs_to_tasks(task_keys, all_prs)

    def fetch_review_prs(self, repo_slugs: list[str]) -> list[PullRequest]:
        if not repo_slugs:
            return []
        from concurrent.futures import ThreadPoolExecutor

        try:
            login = self.whoami()
        except Exception:
            login = ""
        repo_filter = " ".join(f"repo:{s}" for s in repo_slugs)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_requested = pool.submit(
                    self._fetch_search, "review-requested:@me", repo_filter
                )
                fut_reviewed = pool.submit(
                    self._fetch_search, "reviewed-by:@me", repo_filter
                )

            requested = set()
            prs_by_number = {}
            for n in fut_requested.result():
                if n:
                    requested.add(n.get("number"))
                    prs_by_number.setdefault(n["number"], _parse_pr(n))
            for n in fut_reviewed.result():
                if n:
                    prs_by_number.setdefault(n["number"], _parse_pr(n))

            return [
                pr
                for num, pr in prs_by_number.items()
                if num in requested or _latest_review_by(pr, login) != "APPROVED"
            ]
        except (requests.RequestException, KeyError):
            return []

    def is_branch_merged(self, slug: str, branch: str) -> bool:
        if not slug:
            return False
        query = """
        query($owner: String!, $repo: String!, $branch: String!) {
          repository(owner: $owner, name: $repo) {
            pullRequests(headRefName: $branch, states: [MERGED], first: 1) {
              nodes { state }
            }
          }
        }
        """
        owner, repo = slug.split("/", 1)
        try:
            r = self._graphql(query, owner=owner, repo=repo, branch=branch)
            nodes = (
                r.get("data", {})
                .get("repository", {})
                .get("pullRequests", {})
                .get("nodes", [])
            )
            return len(nodes) > 0
        except (requests.RequestException, KeyError):
            return False

    def _graphql(self, query: str, **variables) -> dict:
        body = {"query": query}
        if variables:
            body["variables"] = variables
        r = self._session.post(f"{self._API}/graphql", json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _fetch_search(self, scope: str, repo_filter: str) -> list[dict]:
        q = f"is:pr is:open -author:@me {scope} {repo_filter}"
        r = self._graphql(_REVIEW_QUERY, q=q)
        return r.get("data", {}).get("search", {}).get("nodes", [])
