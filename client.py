#!/usr/bin/env python3

"""
Linear Client Module

Provides a unified client for all Linear API, Git, and GitHub operations.
Handles task management, branch operations, PR creation, and caching.
"""

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


class LinearClient:
    """Unified client for all Linear, Git, and GitHub operations."""

    # Linear API configuration
    LINEAR_API_URL = "https://api.linear.app/graphql"

    # Cache configuration
    CACHE_TTL_SECONDS = 86400  # 1 day (24 * 60 * 60)

    def __init__(self):
        """
        Initialize the LinearClient with configuration from environment variables.

        Loads configuration from .env file in the git repository root, initializes
        the cache, and validates required settings.

        Raises:
            ClientException: If required configuration is missing or invalid
        """
        # Load environment variables from project root directory
        project_root = self.get_git_root()
        load_dotenv(project_root / ".env")

        self.linear_api_key = os.getenv("LINEAR_API_KEY")
        self.linear_team_id = os.getenv("LINEAR_TEAM_ID")
        self.linear_team_key = os.getenv("LINEAR_TEAM_KEY")
        self.linear_workspace = os.getenv("LINEAR_WORKSPACE")  # e.g., "lightricks"

        # Initialize cache
        cache_dir = project_root / ".cache"
        self.cache = dc.Cache(str(cache_dir))

        # Validate configuration
        if not self.linear_api_key:
            raise ClientException(
                "Missing Linear API key. Please set LINEAR_API_KEY "
                "environment variable. Get your API key from: "
                "https://linear.app/settings/api"
            )

        # Need either team ID or team key
        if not self.linear_team_id and not self.linear_team_key:
            raise ClientException(
                "Missing Linear team configuration. Please set either LINEAR_TEAM_ID (UUID) "
                "or LINEAR_TEAM_KEY (e.g., 'ENG', 'SALES') environment variable."
            )

        # If we have team key but no ID, fetch the ID
        if self.linear_team_key and not self.linear_team_id:
            try:
                self.linear_team_id = self._get_team_id_by_key(self.linear_team_key)
            except Exception:
                # If it fails, assume linear_team_key is actually the ID
                self.linear_team_id = self.linear_team_key

    def _make_graphql_request(
        self, query: str, variables: Optional[Dict] = None
    ) -> Dict:
        """
        Make a GraphQL request to Linear API.

        Args:
            query (str): GraphQL query or mutation
            variables (dict, optional): Variables for the query

        Returns:
            dict: Response data from Linear API

        Raises:
            ClientException: If the request fails
        """
        headers = {
            "Authorization": self.linear_api_key,
            "Content-Type": "application/json",
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(
                self.LINEAR_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()

            if "errors" in data:
                error_messages = [
                    error.get("message", str(error)) for error in data["errors"]
                ]
                raise ClientException(f"Linear API error: {', '.join(error_messages)}")

            return data.get("data", {})

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to connect to Linear API: {str(e)}")

    def _get_team_id_by_key(self, team_key: str) -> str:
        """Get team UUID by team key (e.g., 'ENG' -> UUID).

        Args:
            team_key: The team key (e.g., 'ENG', 'SALES')

        Returns:
            The team UUID
        """
        query = """
        {
            teams {
                nodes {
                    id
                    key
                    name
                }
            }
        }
        """

        result = self._make_graphql_request(query)
        teams = result.get("teams", {}).get("nodes", [])

        for team in teams:
            if team.get("key") == team_key:
                return team.get("id")

        raise ClientException(f"Team with key '{team_key}' not found")

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
            if not LinearClient.ensure_git_repo():
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
        task_key = task.get("identifier", "Unknown")

        if not task_key:
            raise ClientException("No task key found")

        # Compute branch name from task key
        branch_name = self.get_feature_branch_name(task_key)

        task_title = task.get("title", "No title")
        pr_title = f"[{task_key}] {task_title}"
        pr_body = ""

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
        Stage all changes and commit with the Linear task title from the current branch.

        Returns:
            str: The commit message used (task title)

        Raises:
            ClientException: If git operations fail or Linear API calls fail
        """
        # Get current branch and extract task key
        current_branch = self.get_current_branch()
        task_key = self.extract_task_key_from_branch(current_branch)

        if not task_key:
            raise ClientException(
                f"Current branch '{current_branch}' does not follow the expected pattern (feature/TASK-KEY)"
            )

        # Fetch task details from Linear
        task = self.get_task_by_key(task_key)
        task_title = task.get("title", "No title available")
        commit_message = task_title.lower()

        # Stage all changes and commit with task title
        self.stage_and_commit_with_title(commit_message)

        return commit_message

    def switch_to_task_branch(self, task_key: str) -> str:
        """
        Switch to the feature branch for the given task key.

        Args:
            task_key (str): The Linear task key

        Returns:
            str: The branch name that was checked out

        Raises:
            ClientException: If git operations fail
        """
        self.checkout_task_branch(task_key, create_new=True)
        return self.get_feature_branch_name(task_key)

    def open_task_in_browser(self, task_key: str):
        """Open a Linear task in the default web browser."""
        if not task_key:
            raise ClientException("No task key found")

        # Construct Linear URL directly
        if self.linear_workspace:
            url = f"https://linear.app/{self.linear_workspace}/issue/{task_key}"
        else:
            # Fallback: use generic linear.app URL (will redirect to correct workspace)
            url = f"https://linear.app/issue/{task_key}"

        webbrowser.open(url)

    def get_viewer_id(self) -> str:
        """
        Get the current user's ID from Linear.

        Returns:
            str: The current user's ID
        """
        query = """
        query {
            viewer {
                id
            }
        }
        """

        result = self._make_graphql_request(query)
        viewer_id = result.get("viewer", {}).get("id")
        if not viewer_id:
            raise ClientException("Could not get viewer ID from Linear")
        return viewer_id

    def get_team_labels(self) -> List[Dict]:
        """Get all labels for the team."""
        query = """
        query TeamLabels($teamId: String!) {
            team(id: $teamId) {
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
            }
        }
        """

        try:
            result = self._make_graphql_request(query, {"teamId": self.linear_team_id})
            return result.get("team", {}).get("labels", {}).get("nodes", [])
        except Exception as e:
            raise ClientException(f"Failed to fetch team labels: {str(e)}")

    def get_team_projects(self) -> List[Dict]:
        """Get all projects for the team."""
        query = """
        query TeamProjects($teamId: String!) {
            team(id: $teamId) {
                projects {
                    nodes {
                        id
                        name
                        description
                        state
                    }
                }
            }
        }
        """

        try:
            result = self._make_graphql_request(query, {"teamId": self.linear_team_id})
            projects = result.get("team", {}).get("projects", {}).get("nodes", [])
            # Filter out completed/canceled projects
            return [
                p for p in projects if p.get("state") not in ["completed", "canceled"]
            ]
        except Exception as e:
            raise ClientException(f"Failed to fetch team projects: {str(e)}")

    def create_task(
        self,
        task_title: str,
        label_ids: List[str] = None,
        priority: int = None,
        project_id: str = None,
    ) -> Dict:
        """Create a new Linear task with optional labels, priority, and project.

        Args:
            task_title: The title of the task
            label_ids: Optional list of label IDs to add to the task
            priority: Optional priority (0=None, 1=Urgent, 2=High, 3=Medium, 4=Low)
            project_id: Optional project ID to add the task to
        """
        # Get current user's ID to assign the task to them
        viewer_id = self.get_viewer_id()

        # Build the input object
        input_fields = {
            "teamId": self.linear_team_id,
            "title": task_title,
            "assigneeId": viewer_id,  # Assign to current user
        }

        # Only add labelIds if we have labels (don't send empty array)
        if label_ids and len(label_ids) > 0:
            input_fields["labelIds"] = label_ids

        # Only add priority if it's set
        if priority is not None:
            input_fields["priority"] = priority

        # Add project if specified
        if project_id:
            input_fields["projectId"] = project_id

        mutation = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                }
            }
        }
        """

        variables = {"input": input_fields}

        try:
            result = self._make_graphql_request(mutation, variables)
            if not result.get("issueCreate", {}).get("success"):
                raise ClientException("Failed to create Linear issue")

            return result.get("issueCreate", {}).get("issue", {})
        except Exception as e:
            # Add more debug info
            raise ClientException(
                f"Failed to create Linear task: {str(e)}. Input: {input_fields}"
            )

    def _fetch_linear_tasks_only(self) -> Dict:
        """
        Fetch only Linear tasks without PR enrichment (for concurrent execution).

        Returns:
            dict: Raw Linear search results
        """
        query = """
        {
            viewer {
                assignedIssues(
                    first: 50
                    orderBy: updatedAt
                    filter: {
                        state: { type: { nin: ["completed", "canceled"] } }
                    }
                ) {
                    nodes {
                        id
                        identifier
                        title
                        state {
                            name
                            type
                        }
                        priority
                        priorityLabel
                        url
                        updatedAt
                    }
                }
            }
        }
        """

        result = self._make_graphql_request(query)
        return {
            "issues": result.get("viewer", {})
            .get("assignedIssues", {})
            .get("nodes", [])
        }

    def get_task_by_key(self, task_key: str) -> Dict:
        """
        Fetch a single Linear task by its identifier.

        Args:
            task_key (str): The Linear task identifier (e.g., "ABC-123")

        Returns:
            dict: Linear task data
        """
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                state {
                    name
                }
                priority
                priorityLabel
                url
                updatedAt
            }
        }
        """

        try:
            result = self._make_graphql_request(query, {"id": task_key})
            issue = result.get("issue")
            if not issue:
                raise ClientException(f"Task {task_key} not found")
            return issue
        except Exception as e:
            raise ClientException(f"Failed to fetch task {task_key}: {str(e)}")

    def fetch_my_incomplete_tasks(self, force_refresh: bool = False) -> Dict:
        """
        Fetch incomplete Linear tasks assigned to the authenticated user and enrich with PR information.
        Uses disk cache for persistent memoization with force_refresh option.

        Args:
            force_refresh (bool): If True, clear cache and fetch fresh data

        Returns:
            dict: Linear search results with tasks enriched with PR information
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
            # Use ThreadPoolExecutor to fetch Linear and GitHub data concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks concurrently
                linear_future = executor.submit(self._fetch_linear_tasks_only)
                pr_future = executor.submit(self._fetch_all_prs)

                # Wait for both to complete and get results
                try:
                    linear_results = linear_future.result(
                        timeout=35
                    )  # Linear has 30s timeout + buffer
                except Exception as e:
                    raise ClientException(f"Failed to fetch Linear tasks: {str(e)}")

                try:
                    all_prs = pr_future.result(timeout=15)  # PR fetch timeout + buffer
                except Exception as e:
                    all_prs = []  # Continue without PR data if GitHub fails

            # Enrich each task with PR information
            issues = linear_results.get("issues", [])
            for task in issues:
                task_key = task.get("identifier", "")
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
            self.cache.set("tasks_data", linear_results, expire=self.CACHE_TTL_SECONDS)

            # Return the enriched and sorted search results
            return linear_results

        except requests.exceptions.RequestException as e:
            raise ClientException(f"Failed to fetch Linear tasks: {str(e)}")

    def get_current_pr_url(self) -> str:
        """
        Get the URL of the current PR.

        Returns:
            str: The PR URL
        """
        try:
            result = subprocess.run(
                ["gh", "pr", "view", "--json", "url"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            if result.stdout.strip():
                pr_data = json.loads(result.stdout)
                return pr_data.get("url", "")
            return ""

        except subprocess.CalledProcessError as e:
            raise ClientException(f"Failed to get PR URL: {str(e)}")
        except json.JSONDecodeError as e:
            raise ClientException(f"Failed to parse PR data: {str(e)}")
        except Exception as e:
            raise ClientException(f"Unexpected error getting PR URL: {str(e)}")
