#!/usr/bin/env python3

import json
import os
import subprocess
import concurrent.futures
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
import diskcache as dc
import humanize

from exceptions import ClientException


class JoraClient:
    """Unified client for all JIRA, Git, and GitHub operations."""

    # JIRA-specific configuration
    MAX_RESULTS = 50
    EXCLUDED_STATUSES = ["Done", "Resolved", "Closed", "Cancelled"]

    # Cache configuration
    CACHE_TTL_SECONDS = 86400  # 1 day (24 * 60 * 60)

    def __init__(self):
        # Load environment variables from project root directory
        project_root = self.get_git_root()
        load_dotenv(project_root / ".env")

        self.jira_url = os.getenv("JIRA_URL")
        self.jira_email = os.getenv("JIRA_EMAIL")
        self.jira_api_key = os.getenv("JIRA_API_KEY")
        self.jira_project_key = os.getenv("JIRA_PROJECT_KEY")

        # Initialize cache
        cache_dir = project_root / ".cache"
        self.cache = dc.Cache(str(cache_dir))

        # Validate configuration
        if not self.jira_url:
            raise ClientException(
                "Missing JIRA URL configuration. Please set JIRA_URL "
                "environment variable (e.g., https://yourcompany.atlassian.net)."
            )

        if not self.jira_email or not self.jira_api_key:
            raise ClientException(
                "Missing required JIRA configuration. Please set JIRA_EMAIL and "
                "JIRA_API_KEY environment variables."
            )

        if not self.jira_project_key:
            raise ClientException(
                "Missing JIRA project configuration. Please set JIRA_PROJECT_KEY "
                "environment variable."
            )

    @staticmethod
    def ensure_git_repo() -> bool:
        """Check if we're in a git repository."""
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def has_uncommitted_changes() -> bool:
        """Check if there are any uncommitted changes in the working directory."""
        try:
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(status_result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def get_git_root() -> Path:
        """Get the root directory of the current git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            # If not in a git repo, fall back to current directory
            return Path.cwd()

    @staticmethod
    def get_current_branch() -> str:
        """Get the name of the current git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise ClientException(f"Failed to get current branch: {str(e)}")

    def get_current_task_key(self) -> str:
        """
        Get the task key from the current branch.

        Returns:
            str: The task key extracted from the current branch

        Raises:
            ClientException: If not on a valid feature branch
        """
        current_branch = self.get_current_branch()
        task_key = self.extract_task_key_from_branch(current_branch)

        if not task_key:
            raise ClientException(
                f"Current branch '{current_branch}' does not follow the expected pattern (feature/TASK-KEY)"
            )

        return task_key

    @staticmethod
    def extract_task_key_from_branch(branch_name: str) -> str:
        """Extract task key from feature branch name. Returns empty string if not a feature branch."""
        if branch_name.startswith("feature/"):
            task_key = branch_name[8:]  # Remove "feature/" prefix
            return task_key.upper()
        return ""

    @staticmethod
    def get_feature_branch_name(task_key: str) -> str:
        """Generate feature branch name from task key."""
        return f"feature/{task_key.lower()}"

    @staticmethod
    def get_all_task_commits() -> str:
        """Get list of all commits for the current task branch (compared to origin/develop)."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "origin/develop..HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    @staticmethod
    def task_branch_has_commits(task_key: str) -> bool:
        """Check if the specified task's branch has any commits compared to develop."""
        try:
            task_branch = f"feature/{task_key}"
            # Check if branch exists and has commits
            result = subprocess.run(
                ["git", "rev-list", "--count", f"origin/develop..{task_branch}"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_count = int(result.stdout.strip())
            return commit_count > 0
        except (subprocess.CalledProcessError, ValueError):
            # Branch doesn't exist or other error - assume no commits
            return False

    @staticmethod
    def get_all_task_changes() -> str:
        """Get diff of all changes in the current task branch compared to origin/develop."""
        try:
            result = subprocess.run(
                ["git", "diff", "origin/develop...HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    @staticmethod
    def get_diff_stats() -> dict:
        """Get statistics about changes in the current task branch compared to origin/develop.

        Returns:
            dict: Contains files_changed, insertions, deletions, and file_list
        """
        try:
            # Get shortstat for summary numbers
            shortstat_result = subprocess.run(
                ["git", "diff", "--shortstat", "origin/develop...HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Get file list with their changes
            numstat_result = subprocess.run(
                ["git", "diff", "--numstat", "origin/develop...HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse shortstat (format: "X files changed, Y insertions(+), Z deletions(-)")
            stats = {
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "file_list": [],
            }

            shortstat = shortstat_result.stdout.strip()
            if shortstat:
                parts = shortstat.split(", ")
                for part in parts:
                    if "file" in part:
                        stats["files_changed"] = int(part.split()[0])
                    elif "insertion" in part:
                        stats["insertions"] = int(part.split()[0])
                    elif "deletion" in part:
                        stats["deletions"] = int(part.split()[0])

            # Parse numstat for per-file statistics
            numstat = numstat_result.stdout.strip()
            if numstat:
                for line in numstat.split("\n"):
                    if line:
                        parts = line.split("\t")
                        if len(parts) >= 3:
                            added = parts[0] if parts[0] != "-" else "0"
                            removed = parts[1] if parts[1] != "-" else "0"
                            filename = parts[2]
                            stats["file_list"].append(
                                {
                                    "file": filename,
                                    "added": int(added) if added.isdigit() else 0,
                                    "removed": int(removed) if removed.isdigit() else 0,
                                }
                            )

            return stats
        except subprocess.CalledProcessError:
            return {
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "file_list": [],
            }

    @staticmethod
    def stage_and_commit_with_title(commit_message: str) -> None:
        """Stage all changes and commit with the given task title."""
        try:
            # Check if we're in a git repository
            if not JoraClient.ensure_git_repo():
                raise ClientException("Not in a git repository")

            # Stage all changes
            subprocess.run(["git", "add", "."], check=True)

            # Check if there are any staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=True,
            )

            if not result.stdout.strip():
                raise ClientException("No changes to commit")

            # Commit the changes
            subprocess.run(["git", "commit", "-m", commit_message], check=True)

        except subprocess.CalledProcessError as e:
            raise ClientException(f"Failed to stage and commit: {str(e)}")

    def checkout_task_branch(self, task_key: str, create_new: bool) -> bool:
        """Checkout the feature branch for the given task key; optionally create it if it doesn't exist.
        If create_new is True and branch doesn't exist, updates local develop from origin/develop
        and creates the branch from develop. Does not perform any rebase operations."""
        try:
            # Compute branch name from task key
            branch_name = self.get_feature_branch_name(task_key)

            # Validate repo and clean state before switching branches
            if not self.ensure_git_repo():
                raise ClientException("Not in a git repository")

            # Check if there are uncommitted changes
            try:
                status_result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if status_result.stdout.strip():
                    raise ClientException(
                        "Please commit or stash changes before switching branches"
                    )
            except subprocess.CalledProcessError:
                raise ClientException(
                    "Please commit or stash changes before switching branches"
                )

            # Try to checkout existing branch
            result = subprocess.run(
                ["git", "checkout", branch_name], capture_output=True
            )
            if result.returncode != 0:
                if create_new:
                    # Branch doesn't exist:
                    # 1) Update develop from origin/develop
                    try:
                        subprocess.run(["git", "fetch", "origin"], check=True)
                        subprocess.run(["git", "checkout", "develop"], check=True)
                        subprocess.run(["git", "pull", "origin", "develop"], check=True)
                    except subprocess.CalledProcessError:
                        raise ClientException(
                            "Could not update develop branch - ensure it exists"
                        )
                    # 2) Create new branch from updated develop
                    subprocess.run(
                        ["git", "checkout", "-b", branch_name, "develop"], check=True
                    )
                else:
                    # Branch doesn't exist and we're not allowed to create it
                    raise ClientException(
                        "Branch does not exist - no changes to create PR from"
                    )

            return True
        except subprocess.CalledProcessError as e:
            raise ClientException(f"Failed to checkout branch: {str(e)}")

    @staticmethod
    def check_pr_exists() -> bool:
        """Check if a PR exists for the current branch.

        Returns:
            bool: True if a PR exists for the current branch, False otherwise
        """
        try:
            result = subprocess.run(
                ["gh", "pr", "view", "--json", "number"],
                capture_output=True,
                text=True,
                check=False,  # Don't raise exception on non-zero exit code
            )
            # If the command succeeds and returns JSON, a PR exists
            return result.returncode == 0 and result.stdout.strip() != ""
        except Exception:
            return False

    def _fetch_all_prs(self) -> List[Dict]:
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

    def _find_pr_by_content(self, content: str, all_prs: List[Dict]) -> Optional[Dict]:
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

    def _get_pr_sort_priority(self, task: Dict) -> int:
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

    def create_new_pr(self, task: Dict):
        """Create a new PR for the given task."""
        task_key = task.get("key", "Unknown")

        if not task_key:
            raise ClientException("No task key found")

        # Compute branch name from task key
        branch_name = self.get_feature_branch_name(task_key)

        pr_title = f"[{task_key}] {task.get("fields", {}).get("summary", "No summary")}"
        pr_body = f"[{task_key}]\n\n---\n*Created by [Jora](https://github.com/dodeca-6-tope/jora)*"

        try:
            # Ensure we're in a git repository
            if not self.ensure_git_repo():
                raise ClientException("Not in a git repository")

            # Switch to existing feature branch (don't create new as it would have no changes)
            try:
                self.checkout_task_branch(task_key, create_new=False)
            except ClientException as e:
                raise ClientException(str(e))

            # Check for changes to commit
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--name-only", "origin/develop"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if not diff_result.stdout.strip():
                    raise ClientException("No changes found to create a PR")
            except subprocess.CalledProcessError as e:
                raise ClientException(f"Failed to check for changes: {str(e)}")

            # Push branch and create PR
            try:
                subprocess.run(
                    ["git", "push", "--set-upstream", "origin", branch_name], check=True
                )
            except subprocess.CalledProcessError as e:
                raise ClientException(f"Failed to push branch: {str(e)}")

            subprocess.run(
                ["gh", "pr", "create", "--title", pr_title, "--body", pr_body],
                check=True,
            )

            return branch_name

        except subprocess.CalledProcessError as e:
            raise ClientException(f"Failed to create PR: {str(e)}")
        except Exception as e:
            raise ClientException(f"Failed to create PR: {str(e)}")

    def commit_current_task(self) -> str:
        """
        Stage all changes and commit with the JIRA task title from the current branch.

        Returns:
            str: The commit message used (task title)

        Raises:
            ClientException: If git operations fail or JIRA API calls fail
        """
        # Get current branch and extract task key
        current_branch = self.get_current_branch()
        task_key = self.extract_task_key_from_branch(current_branch)

        if not task_key:
            raise ClientException(
                f"Current branch '{current_branch}' does not follow the expected pattern (feature/TASK-KEY)"
            )

        # Fetch task details from JIRA
        task = self.get_task_by_key(task_key)
        task_title = task.get("fields", {}).get("summary", "No title available")
        commit_message = task_title.lower()

        # Stage all changes and commit with task title
        self.stage_and_commit_with_title(commit_message)

        return commit_message

    def switch_to_task_branch(self, task_key: str) -> str:
        """
        Switch to the feature branch for the given task key.

        Args:
            task_key (str): The JIRA task key

        Returns:
            str: The branch name that was checked out

        Raises:
            ClientException: If git operations fail
        """
        self.checkout_task_branch(task_key, create_new=True)
        return self.get_feature_branch_name(task_key)

    def open_task_in_browser(self, task_key: str):
        """Open a JIRA task in the default web browser."""
        if not task_key:
            raise ClientException("No task key found")

        webbrowser.open(f"{self.jira_url.rstrip('/')}/browse/{task_key}")

    def get_project_name(self) -> str:
        """Get the project key for display purposes."""
        return self.jira_project_key

    def _get_account_id_by_email(self, email: str) -> str:
        """
        Get JIRA account ID using email address.

        Args:
            email (str): Email address to search for

        Returns:
            str: The account ID for the user
        """
        # Prepare the API endpoint for user search
        url = f"{self.jira_url.rstrip('/')}/rest/api/3/user/search"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Accept": "application/json"}

        # Search parameters
        params = {"query": email, "maxResults": 1}

        try:
            response = requests.get(
                url, auth=auth, headers=headers, params=params, timeout=30
            )
            response.raise_for_status()

            users = response.json()
            if not users:
                raise ClientException(f"No user found with email: {email}")

            account_id = users[0].get("accountId")
            if not account_id:
                raise ClientException(f"Account ID not found for user: {email}")

            return account_id

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to get account ID: {str(e)}")

    def get_project_components(self, project_key: str) -> List[str]:
        """Get all available components for the specified project."""
        try:
            url = f"{self.jira_url.rstrip('/')}/rest/api/3/project/{project_key}/components"
            auth = (self.jira_email, self.jira_api_key)
            headers = {"Accept": "application/json"}

            response = requests.get(url, auth=auth, headers=headers, timeout=30)
            response.raise_for_status()

            components = response.json()
            return [comp.get("name", "") for comp in components if comp.get("name")]

        except Exception as e:
            raise ClientException(f"Failed to fetch components: {str(e)}")

    def create_task(self, task_title: str, component_names: List[str]) -> Dict:
        """Create a new JIRA task with user input."""
        # Prepare the API endpoint for creating issues
        url = f"{self.jira_url.rstrip('/')}/rest/api/3/issue"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Get account ID for assignment
        account_id = self._get_account_id_by_email(self.jira_email)

        # Prepare the issue data
        issue_data = {
            "fields": {
                "project": {"key": self.jira_project_key},
                "summary": task_title,
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": "Task created via Jora script"}
                            ],
                        }
                    ],
                },
                "issuetype": {"name": "Task"},  # Default issue type
                "assignee": {"accountId": account_id},
            }
        }

        # Add components if specified
        if component_names:
            issue_data["fields"]["components"] = [
                {"name": name} for name in component_names
            ]

        try:
            # Make the API request
            response = requests.post(
                url, auth=auth, headers=headers, data=json.dumps(issue_data), timeout=30
            )

            # Check if request was successful
            if response.status_code == 201:
                created_task = response.json()
                return created_task
            else:
                error_msg = (
                    f"Failed to create task. Status: {response.status_code}, "
                    f"Response: {response.text}"
                )
                # If component-related error, provide helpful message
                if component_names and "component" in response.text.lower():
                    error_msg += (
                        f" (Component issue with: '{', '.join(component_names)}')"
                    )
                raise ClientException(error_msg)

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to create JIRA task: {str(e)}")

    def _fetch_jira_tasks_only(self) -> Dict:
        """
        Fetch only JIRA tasks without PR enrichment (for concurrent execution).

        Returns:
            dict: Raw JIRA search results
        """
        # Get account ID for the search
        account_id = self._get_account_id_by_email(self.jira_email)

        # Prepare the API endpoint for search (v3)
        url = f"{self.jira_url.rstrip('/')}/rest/api/3/search/jql"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Build JQL query for incomplete tasks
        # Create the status exclusion part of the query
        status_exclusion = " AND ".join(
            [f'status != "{status}"' for status in self.EXCLUDED_STATUSES]
        )

        jql = f'assignee = "{account_id}" AND {status_exclusion} ORDER BY updated DESC'

        # Prepare query parameters for v3 GET request
        params = {
            "jql": jql,
            "maxResults": self.MAX_RESULTS,
            "fields": "key,summary,status,priority",
            "startAt": 0,
            "expand": "changelog",
        }

        # Make the API request using GET instead of POST for v3
        response = requests.get(
            url,
            auth=auth,
            headers=headers,
            params=params,
            timeout=30,
        )

        # Check if request was successful
        response.raise_for_status()

        # Get the search results
        return response.json()

    def get_task_by_key(self, task_key: str) -> Dict:
        """
        Fetch a single JIRA task by its key.

        Args:
            task_key (str): The JIRA task key (e.g., "ABC-123")

        Returns:
            dict: JIRA task data
        """
        # Prepare the API endpoint for getting an issue
        url = f"{self.jira_url.rstrip('/')}/rest/api/3/issue/{task_key}"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Accept": "application/json"}

        try:
            # Make the API request
            response = requests.get(
                url,
                auth=auth,
                headers=headers,
                timeout=30,
            )

            # Check if request was successful
            response.raise_for_status()

            # Get the task data
            return response.json()

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to fetch task {task_key}: {str(e)}")

    def get_task_comments(self, task_key: str) -> List[Dict]:
        """
        Fetch all comments for a JIRA task.

        Args:
            task_key (str): The JIRA task key (e.g., "ABC-123")

        Returns:
            list: List of comment data from JIRA API
        """
        # Prepare the API endpoint for getting task comments
        url = f"{self.jira_url.rstrip('/')}/rest/api/3/issue/{task_key}/comment"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Accept": "application/json"}

        try:
            # Make the API request
            response = requests.get(
                url,
                auth=auth,
                headers=headers,
                timeout=30,
            )

            # Check if request was successful
            response.raise_for_status()

            # Get the comments data
            result = response.json()
            return result.get("comments", [])

        except requests.exceptions.RequestException as e:
            raise ClientException(
                f"Failed to fetch comments for task {task_key}: {str(e)}"
            )

    @staticmethod
    def extract_adf_content(adf_description: dict) -> tuple[str, list[str]]:
        """
        Extract plain text and media URLs from JIRA's Atlassian Document Format (ADF).

        Args:
            adf_description (dict): ADF formatted description from JIRA API

        Returns:
            tuple: (description_text, list_of_media_urls)
        """
        if not adf_description or not isinstance(adf_description, dict):
            return "", []

        text_parts = []
        media_urls = []

        def extract_recursive(content):
            """Recursively extract text and media from ADF content."""
            if isinstance(content, dict):
                node_type = content.get("type", "")

                # Extract text nodes
                if node_type == "text":
                    text_parts.append(content.get("text", ""))

                # Extract media nodes (images, files, etc.)
                elif node_type in ("media", "mediaInline", "mediaSingle"):
                    attrs = content.get("attrs", {})
                    # Media nodes can have 'id' for attachments or direct 'url'
                    media_id = attrs.get("id")
                    if media_id:
                        # For JIRA Cloud, construct attachment URL
                        # Note: The actual URL construction depends on your JIRA setup
                        media_urls.append(f"attachment:{media_id}")
                    elif attrs.get("url"):
                        media_urls.append(attrs["url"])

                # Recurse into nested content
                if "content" in content:
                    for child in content["content"]:
                        extract_recursive(child)

            elif isinstance(content, list):
                for item in content:
                    extract_recursive(item)

        extract_recursive(adf_description)
        return " ".join(text_parts).strip(), media_urls

    def get_jira_comments_context(self, task_key: str) -> str:
        """
        Get formatted context for Jira task comments and description.

        Args:
            task_key (str): The JIRA task key

        Returns:
            str: Formatted context including task description and comments
        """
        try:
            # Fetch task details and comments
            task = self.get_task_by_key(task_key)
            comments = self.get_task_comments(task_key)

            task_summary = task.get("fields", {}).get("summary", "No summary")
            task_description = task.get("fields", {}).get("description", {})

            # Extract description text
            description_text, _ = self.extract_adf_content(task_description)

            # Build context
            context = f"**JIRA Task: {task_key}**\n"
            context += f"**Summary:** {task_summary}\n\n"

            if description_text:
                context += f"**Description:**\n{description_text}\n\n"

            if comments:
                context += "**Comments:**\n"
                for i, comment in enumerate(comments, 1):
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    created = comment.get("created", "Unknown date")
                    body = comment.get("body", {})

                    # Extract comment text from ADF format
                    comment_text, _ = self.extract_adf_content(body)

                    if comment_text:
                        context += f"{i}. **{author}** ({created}):\n{comment_text}\n\n"

            return context

        except ClientException:
            # If we can't fetch Jira data, return empty context
            return ""

    def get_task_context(self, task_key: Optional[str] = None) -> str:
        """Generate task context string with summary, description, and attachments.

        Args:
            task_key (str, optional): The JIRA task key. If not provided, uses current branch task.

        Returns:
            Formatted string containing task information
        """
        # Get task key from current branch if not provided
        if not task_key:
            task_key = self.get_current_task_key()

        # Fetch task details
        task = self.get_task_by_key(task_key)

        # Extract task information
        task_summary = task.get("fields", {}).get("summary", "No summary")
        task_description = task.get("fields", {}).get("description", {})

        # Extract description text and media URLs
        description_text, media_urls = self.extract_adf_content(task_description)

        # Build task context
        context = f"**Task:** {task_key}\n" f"**Summary:** {task_summary}\n\n"

        if description_text:
            context += f"**Description:**\n{description_text}\n\n"

        if media_urls:
            context += "**Images/Attachments:**\n"
            for i, url in enumerate(media_urls, 1):
                context += f"{i}. {url}\n"
            context += "\n"

        return context

    def get_cache_timestamp_formatted(self) -> Optional[str]:
        """Get the cache timestamp in a user-friendly format."""
        # Get tasks data with expiration metadata to calculate insertion time
        result = self.cache.get("tasks_data", expire_time=True)
        if not result or result[0] is None:
            return None

        _, expire_time = result
        # Check if expire_time is None (cache entry without expiration)
        if expire_time is None:
            return None

        # Calculate insertion time by subtracting TTL from expiration time
        store_time = datetime.fromtimestamp(expire_time - self.CACHE_TTL_SECONDS)
        return f"Updated {humanize.naturaltime(store_time)}"

    def fetch_my_incomplete_tasks(self, force_refresh: bool = False) -> Dict:
        """
        Fetch incomplete JIRA tasks assigned to the authenticated user and enrich with PR information.
        Uses disk cache for persistent memoization with force_refresh option.

        Args:
            force_refresh (bool): If True, clear cache and fetch fresh data

        Returns:
            dict: JIRA search results with tasks enriched with PR information
        """
        # Clear the cache if force refresh is requested
        if force_refresh:
            self.cache.clear()

        # Check if we have cached data (diskcache handles expiration automatically)
        cached_data = self.cache.get("tasks_data")
        if cached_data is not None:
            return cached_data

        # No cached data, fetch fresh
        fetch_time = datetime.now()

        try:
            # Use ThreadPoolExecutor to fetch JIRA and GitHub data concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks concurrently
                jira_future = executor.submit(self._fetch_jira_tasks_only)
                pr_future = executor.submit(self._fetch_all_prs)

                # Wait for both to complete and get results
                try:
                    jira_results = jira_future.result(
                        timeout=35
                    )  # JIRA has 30s timeout + buffer
                except Exception as e:
                    raise ClientException(f"Failed to fetch JIRA tasks: {str(e)}")

                try:
                    all_prs = pr_future.result(timeout=15)  # PR fetch timeout + buffer
                except Exception as e:
                    all_prs = []  # Continue without PR data if GitHub fails

            # Enrich each task with PR information
            issues = jira_results.get("issues", [])
            for task in issues:
                task_key = task.get("key", "")
                pr_info = self._find_pr_by_content(task_key, all_prs)
                # Add PR information to the task
                if pr_info:
                    task["_pr_url"] = pr_info.get("url")
                    task["_has_pr"] = True
                    task["_pr_reviews"] = pr_info.get("reviews", [])
                    task["_pr_state"] = pr_info.get("state")
                else:
                    task["_pr_url"] = None
                    task["_has_pr"] = False
                    task["_pr_reviews"] = []
                    task["_pr_state"] = None

            # Sort tasks by PR status priority
            issues.sort(key=self._get_pr_sort_priority)

            # Cache the results with 1 day expiration
            self.cache.set("tasks_data", jira_results, expire=self.CACHE_TTL_SECONDS)

            # Return the enriched and sorted search results
            return jira_results

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to fetch JIRA tasks: {str(e)}")
