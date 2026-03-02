import json
import re
import subprocess
from typing import Dict, List


def fetch_prs() -> List[Dict]:
    """Fetch open PRs via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--json", "url,title,headRefName,body,reviews,statusCheckRollup", "--limit", "100"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return []
    except (subprocess.SubprocessError, json.JSONDecodeError):
        return []


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
