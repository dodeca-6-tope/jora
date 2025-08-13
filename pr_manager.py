#!/usr/bin/env python3

import json
import subprocess
from typing import Dict, List, Optional

from git_operations import GitOperations
from exceptions import PRManagerException


class PRManager:
    """Handle PR-related operations and analysis."""

    def __init__(self):
        self.git_ops = GitOperations()

    def fetch_all_prs(self) -> List[Dict]:
        """Fetch all open PRs once for caching. Returns list of PR objects with approval status."""
        try:
            # Use GitHub CLI with official JSON fields from documentation
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--json",
                    "url,title,headRefName,body,reviews,state",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            return []
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            return []  # Return empty list if any error occurs

    def find_pr_for_task_from_cache(
        self, task: Dict, all_prs: List[Dict]
    ) -> Optional[Dict]:
        """Find an existing PR for the given task from cached PR data. Returns PR info dict if found, None otherwise."""
        task_key = task.get("key", "")
        if not task_key:
            return None

        # Check for task key in title, branch name, or body
        for pr in all_prs:
            if (
                task_key.upper() in pr.get("title", "").upper()
                or task_key.lower() in pr.get("headRefName", "").lower()
                or task_key.upper() in pr.get("body", "").upper()
            ):
                return {
                    "url": pr.get("url"),
                    "reviews": pr.get("reviews", []),
                    "state": pr.get("state"),
                }
        return None

    def analyze_pr_reviews(self, reviews: List[Dict]) -> str:
        """
        Analyze PR reviews to determine the overall status.

        Args:
            reviews (list): List of review objects from GitHub API

        Returns:
            str: Review status - 'APPROVED', 'CHANGES_REQUESTED', 'REVIEW_REQUIRED', or 'NO_REVIEWS'
        """
        if not reviews:
            return "NO_REVIEWS"

        # Get the latest review from each reviewer
        reviewer_latest_reviews = {}
        for review in reviews:
            reviewer = review.get("author", {}).get("login", "")
            if reviewer:
                # Keep only the most recent review from each reviewer (reviews are typically ordered by date)
                reviewer_latest_reviews[reviewer] = review

        latest_reviews = list(reviewer_latest_reviews.values())

        # Check if any reviewer requested changes
        if any(review.get("state") == "CHANGES_REQUESTED" for review in latest_reviews):
            return "CHANGES_REQUESTED"

        # Check if at least one review is approved
        approved_reviews = [
            review for review in latest_reviews if review.get("state") == "APPROVED"
        ]
        if approved_reviews:
            return "APPROVED"

        # If there are reviews but not all approved, review is still required
        return "REVIEW_REQUIRED"

    def get_pr_sort_priority(self, task: Dict) -> int:
        """
        Get sort priority for task based on PR status.
        Lower numbers = higher priority (sorted first).

        Args:
            task (dict): Task with PR information

        Returns:
            int: Sort priority (0=highest, 4=lowest)
        """
        if not task.get("_has_pr"):
            return 4  # No PR - lowest priority

        reviews = task.get("_pr_reviews", [])
        review_status = self.analyze_pr_reviews(reviews)

        if review_status == "APPROVED":
            return 0  # All reviews approved - highest priority
        elif review_status == "CHANGES_REQUESTED" or review_status == "REVIEW_REQUIRED":
            return 1  # Has reviews (approved or changes requested) - second priority
        else:  # NO_REVIEWS
            return 2  # PR exists but no reviews - third priority

    def get_existing_pr_url(self, task: Dict) -> str:
        """Get the PR URL for the given task using cached information. Returns PR URL."""
        task_key = task.get("key", "")
        if not task_key:
            raise PRManagerException("No task key found")

        # Use cached PR URL if available
        pr_url = task.get("_cached_pr_url")

        if pr_url:
            return pr_url
        else:
            raise PRManagerException(f"No PR found for {task_key}")

    def create_new_pr(self, task: Dict) -> str:
        """Create a new PR for the given task. Automatically handles branch creation and switching. Returns branch name."""
        task_key = task.get("key", "")
        task_summary = task.get("fields", {}).get("summary", "No summary")

        if not task_key:
            raise PRManagerException("No task key found")

        branch_name = f"feature/{task_key.lower()}"
        pr_title = f"[{task_key}] {task_summary}"

        try:
            # Ensure we're in a git repository
            if not self.git_ops.ensure_git_repo():
                raise PRManagerException("Not in a git repository")

            # Update develop branch to latest
            if not self.git_ops.update_develop_branch():
                raise PRManagerException("Failed to update develop branch")

            # Automatically switch to or create the feature branch
            if not self.git_ops.switch_and_rebase_branch(branch_name):
                raise PRManagerException("Failed to switch to feature branch")

            # Check for changes to commit
            result = subprocess.run(
                ["git", "diff", "--name-only", "develop"],
                capture_output=True,
                text=True,
            )

            if not result.stdout.strip():
                raise PRManagerException("No changes found to create a PR")

            # Push branch and create PR
            subprocess.run(
                ["git", "push", "--set-upstream", "origin", branch_name], check=True
            )

            subprocess.run(
                ["gh", "pr", "create", "--title", pr_title, "--body", ""], check=True
            )

            return branch_name

        except subprocess.CalledProcessError as e:
            raise PRManagerException(f"Failed to create PR: {str(e)}")
        except Exception as e:
            raise PRManagerException(f"Failed to create PR: {str(e)}")
