#!/usr/bin/env python3

import json
import subprocess
from typing import Dict, List, Optional

from .git import GitOperations
from exceptions import PRManagerException


class PRManager:
    """Handle PR-related operations and analysis."""

    def __init__(self):
        self.git_ops = GitOperations()

    def fetch_all_prs(self) -> List[Dict]:
        """Fetch all open PRs once for caching. Returns list of PR objects with approval status."""
        try:
            # Use GitHub CLI with minimal required fields for better performance
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--json",
                    "url,title,headRefName,body,reviews,state",
                    "--limit",
                    "100",  # Limit to reasonable number for performance
                ],
                capture_output=True,
                text=True,
                timeout=8,  # Reduced from 10s to 8s
            )

            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
            return []
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            return []  # Return empty list if any error occurs

    def find_pr_by_content(
        self, content: str, all_prs: List[Dict]
    ) -> Optional[Dict]:
        """Find an existing PR that contains the given content from a list of PRs. Returns PR info dict if found, None otherwise."""
        if not content:
            return None

        # Check for content in title, branch name, or body
        for pr in all_prs:
            if (
                content.upper() in pr.get("title", "").upper()
                or content.lower() in pr.get("headRefName", "").lower()
                or content.upper() in pr.get("body", "").upper()
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

    def create_new_pr(self, branch_name: str, task: Dict):
        task_key = task.get("key", "Unknown")

        if not task_key:
            raise PRManagerException("No task key found")

        pr_title = f"[{task_key}] {task.get("fields", {}).get("summary", "No summary")}"
        pr_body = f"[{task_key}]\n\n---\n*Created by [Jora](https://github.com/dodeca-6-tope/jora)*"
        
        try:
            # Ensure we're in a git repository
            if not self.git_ops.ensure_git_repo():
                raise PRManagerException("Not in a git repository")

            # Switch to existing feature branch (don't create new as it would have no changes)
            try:
                self.git_ops.checkout_branch(branch_name, create_new=False)
            except GitOperationsException as e:
                raise PRManagerException(str(e))

            # Check for changes to commit
            if not self.git_ops.has_changes_from_branch("develop"):
                raise PRManagerException("No changes found to create a PR")

            # Push branch and create PR
            self.git_ops.push_branch_with_upstream(branch_name)
            
            subprocess.run(
                ["gh", "pr", "create", "--title", pr_title, "--body", pr_body],
                check=True,
            )

            return branch_name

        except subprocess.CalledProcessError as e:
            raise PRManagerException(f"Failed to create PR: {str(e)}")
        except Exception as e:
            raise PRManagerException(f"Failed to create PR: {str(e)}")
