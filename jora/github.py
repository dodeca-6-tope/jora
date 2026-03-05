import json
import re
import subprocess
from typing import Dict, List

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

_AUTHORED_QUERY = """
{
  search(query: "is:pr is:open author:@me", type: ISSUE, first: 100) {
    nodes { %s }
  }
}
""" % _PR_FIELDS

_REVIEW_QUERY = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    nodes { %s }
  }
}
""" % _PR_FIELDS


def repo_slug(repo_dir: str) -> str:
    """Get 'owner/name' from the git remote URL. No network call."""
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, cwd=repo_dir,
        )
        url = r.stdout.strip()
        if not url:
            return ""
        # git@github.com:owner/repo.git or https://github.com/owner/repo.git
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        return m.group(1) if m else ""
    except subprocess.SubprocessError:
        return ""


def is_pr_merged(repo_dir: str, branch: str) -> bool:
    """Check if the PR for a branch has been merged."""
    try:
        r = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state", "-q", ".state"],
            capture_output=True, text=True, timeout=10, cwd=repo_dir,
        )
        return r.stdout.strip() == "MERGED"
    except subprocess.SubprocessError:
        return False


def fetch_prs() -> List[Dict]:
    """Fetch all open PRs authored by the current gh user."""
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={_AUTHORED_QUERY}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        nodes = json.loads(result.stdout).get("data", {}).get("search", {}).get("nodes", [])
        return [_normalize_pr(n) for n in nodes if n]
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


_gh_user_cache = None

def warm_gh_user() -> str:
    global _gh_user_cache
    if _gh_user_cache is not None:
        return _gh_user_cache
    try:
        r = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            capture_output=True, text=True, timeout=10,
        )
        _gh_user_cache = r.stdout.strip() if r.returncode == 0 else ""
    except subprocess.SubprocessError:
        _gh_user_cache = ""
    return _gh_user_cache


def _my_latest_review(pr: Dict, login: str) -> str:
    """Return the user's latest review state on a PR, or empty string."""
    for r in reversed(pr.get("reviews", [])):
        if r.get("author", {}).get("login") == login:
            return r["state"]
    return ""


def _fetch_search(scope: str, repo_filter: str) -> List[Dict]:
    q = f"is:pr is:open -author:@me {scope} {repo_filter}"
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={_REVIEW_QUERY}", "-f", f"q={q}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return json.loads(result.stdout).get("data", {}).get("search", {}).get("nodes", [])


def fetch_review_prs(repo_slugs: List[str]) -> List[Dict]:
    """Fetch open PRs needing attention: requested or reviewed but not yet approved."""
    if not repo_slugs:
        return []
    from concurrent.futures import ThreadPoolExecutor

    login = warm_gh_user()
    repo_filter = " ".join(f"repo:{s}" for s in repo_slugs)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_requested = pool.submit(_fetch_search, "review-requested:@me", repo_filter)
            fut_reviewed = pool.submit(_fetch_search, "reviewed-by:@me", repo_filter)

        requested = set()
        prs_by_number = {}
        for n in fut_requested.result():
            if n:
                requested.add(n.get("number"))
                prs_by_number.setdefault(n["number"], _normalize_pr(n))
        for n in fut_reviewed.result():
            if n:
                prs_by_number.setdefault(n["number"], _normalize_pr(n))

        return [
            pr for num, pr in prs_by_number.items()
            if num in requested or _my_latest_review(pr, login) != "APPROVED"
        ]
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _normalize_pr(node: Dict) -> Dict:
    reviews = [
        {"state": r["state"], "author": r.get("author", {})}
        for r in (node.get("reviews", {}).get("nodes", []) or [])
    ]
    commits = node.get("commits", {}).get("nodes", []) or []
    checks = []
    if commits:
        rollup = commits[0].get("commit", {}).get("statusCheckRollup") or {}
        checks = [
            {"conclusion": ctx.get("conclusion") or ctx.get("state") or ""}
            for ctx in (rollup.get("contexts", {}).get("nodes", []) or [])
        ]
    return {
        "number": node.get("number"),
        "title": node.get("title", ""),
        "url": node.get("url", ""),
        "body": node.get("body", ""),
        "headRefName": node.get("headRefName", ""),
        "author": (node.get("author") or {}).get("login", ""),
        "repoSlug": (node.get("repository") or {}).get("nameWithOwner", ""),
        "reviews": reviews,
        "statusCheckRollup": checks,
    }


def match_prs_to_tasks(task_keys: List[str], all_prs: List[Dict]) -> Dict[str, List[Dict]]:
    """Returns {task_key: [matching_prs]} for each task that has PRs."""
    result = {}
    for key in task_keys:
        pattern = re.compile(re.escape(key) + r"(?!\w)", re.IGNORECASE)
        matches = [
            pr for pr in all_prs
            if pattern.search(pr.get("title", ""))
            or pattern.search(pr.get("headRefName", ""))
            or pattern.search(pr.get("body", ""))
        ]
        matches.sort(key=lambda pr: 0 if pattern.search(pr.get("headRefName", "")) else 1)
        if matches:
            result[key] = matches
    return result


def analyze_ci(checks: List[Dict]) -> str:
    """Returns SUCCESS, FAILURE, PENDING, or NONE."""
    if not checks:
        return "NONE"
    if all(c.get("conclusion") == "SUCCESS" for c in checks):
        return "SUCCESS"
    if any(c.get("conclusion") == "FAILURE" for c in checks):
        return "FAILURE"
    return "PENDING"


def analyze_reviews(reviews: List[Dict]) -> str:
    """Returns APPROVED, CHANGES_REQUESTED, REVIEW_REQUIRED, or NO_REVIEWS."""
    if not reviews:
        return "NO_REVIEWS"
    latest_by_reviewer = {}
    for r in reviews:
        login = r.get("author", {}).get("login", "")
        if login:
            latest_by_reviewer[login] = r
    latest = list(latest_by_reviewer.values())
    if any(r["state"] == "CHANGES_REQUESTED" for r in latest):
        return "CHANGES_REQUESTED"
    if any(r["state"] == "APPROVED" for r in latest):
        return "APPROVED"
    return "REVIEW_REQUIRED"
