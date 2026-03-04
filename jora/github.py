import json
import re
import subprocess
from typing import Dict, List

_GRAPHQL_QUERY = """
{
  search(query: "is:pr is:open author:@me", type: ISSUE, first: 100) {
    nodes {
      ... on PullRequest {
        title
        url
        body
        headRefName
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
    }
  }
}
"""


def fetch_prs() -> List[Dict]:
    """Fetch all open PRs authored by the current gh user via GraphQL (single call)."""
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={_GRAPHQL_QUERY}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        nodes = data.get("data", {}).get("search", {}).get("nodes", [])
        return [_normalize_pr(n) for n in nodes if n]
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


def _normalize_pr(node: Dict) -> Dict:
    """Convert GraphQL response shape to the flat shape the rest of the code expects."""
    reviews = [
        {"state": r["state"], "author": r.get("author", {})}
        for r in (node.get("reviews", {}).get("nodes", []) or [])
    ]

    checks = []
    commits = node.get("commits", {}).get("nodes", []) or []
    if commits:
        rollup = commits[0].get("commit", {}).get("statusCheckRollup") or {}
        for ctx in (rollup.get("contexts", {}).get("nodes", []) or []):
            conclusion = ctx.get("conclusion") or ctx.get("state") or ""
            checks.append({"conclusion": conclusion})

    return {
        "title": node.get("title", ""),
        "url": node.get("url", ""),
        "body": node.get("body", ""),
        "headRefName": node.get("headRefName", ""),
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
