#!/usr/bin/env python3

import json
from typing import Dict, List, Optional

import requests

from config import Config
from pr_manager import PRManager
from exceptions import JiraAPIException


class JiraAPI:
    """Handle all JIRA API operations."""

    def __init__(self, config: Config):
        self.config = config
        self.pr_manager = PRManager()

    def get_account_id_by_email(self, email: str) -> str:
        """
        Get JIRA account ID using email address.

        Args:
            email (str): Email address to search for

        Returns:
            str: The account ID for the user
        """
        # Prepare the API endpoint for user search
        url = f"{self.config.jira_url.rstrip('/')}/rest/api/2/user/search"

        # Prepare authentication
        auth = (self.config.jira_email, self.config.jira_api_key)

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
                raise JiraAPIException(f"No user found with email: {email}")

            account_id = users[0].get("accountId")
            if not account_id:
                raise JiraAPIException(f"Account ID not found for user: {email}")

            return account_id

        except requests.exceptions.RequestException as e:
            raise JiraAPIException(f"Failed to get account ID: {str(e)}")

    def get_project_components(self, project_key: str) -> List[str]:
        """Get all available components for the specified project."""
        try:
            url = f"{self.config.jira_url.rstrip('/')}/rest/api/2/project/{project_key}/components"
            auth = (self.config.jira_email, self.config.jira_api_key)
            headers = {"Accept": "application/json"}

            response = requests.get(url, auth=auth, headers=headers, timeout=30)
            response.raise_for_status()

            components = response.json()
            return [comp.get("name", "") for comp in components if comp.get("name")]

        except Exception as e:
            raise JiraAPIException(f"Failed to fetch components: {str(e)}")

    def create_task(self, task_title: str, component_names: List[str]) -> Dict:
        """Create a new JIRA task with user input."""
        # Prepare the API endpoint for creating issues
        url = f"{self.config.jira_url.rstrip('/')}/rest/api/2/issue"

        # Prepare authentication
        auth = (self.config.jira_email, self.config.jira_api_key)

        # Prepare headers
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Get account ID for assignment
        account_id = self.get_account_id_by_email(self.config.jira_email)

        # Prepare the issue data
        issue_data = {
            "fields": {
                "project": {"key": self.config.jira_project_key},
                "summary": task_title,
                "description": f"Task created via JIRA Task Manager script",
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
                raise JiraAPIException(error_msg)

        except requests.exceptions.RequestException as e:
            raise JiraAPIException(f"Failed to create JIRA task: {str(e)}")

    def fetch_my_incomplete_tasks(self) -> Dict:
        """
        Fetch incomplete JIRA tasks assigned to the authenticated user and enrich with PR information.

        Returns:
            dict: JIRA search results with tasks enriched with PR information
        """
        # Get account ID for the search
        account_id = self.get_account_id_by_email(self.config.jira_email)

        # Prepare the API endpoint for search
        url = f"{self.config.jira_url.rstrip('/')}/rest/api/2/search"

        # Prepare authentication
        auth = (self.config.jira_email, self.config.jira_api_key)

        # Prepare headers
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Build JQL query for incomplete tasks
        # Create the status exclusion part of the query
        status_exclusion = " AND ".join(
            [f'status != "{status}"' for status in self.config.excluded_statuses]
        )

        jql = f'assignee = "{account_id}" AND {status_exclusion} ORDER BY updated DESC'

        # Prepare the search data
        search_data = {
            "jql": jql,
            "maxResults": self.config.max_results,
            "fields": ["summary", "status", "priority"],
            "expand": ["changelog"],  # This might contain development info
        }

        try:
            # Make the API request
            response = requests.post(
                url,
                auth=auth,
                headers=headers,
                data=json.dumps(search_data),
                timeout=30,
            )

            # Check if request was successful
            response.raise_for_status()

            # Get the search results
            jira_results = response.json()

            # Fetch all PRs once for caching
            all_prs = self.pr_manager.fetch_all_prs()

            # Enrich each task with PR information
            issues = jira_results.get("issues", [])
            for task in issues:
                pr_info = self.pr_manager.find_pr_for_task_from_cache(task, all_prs)
                # Add PR information to the task
                if pr_info:
                    task["_cached_pr_url"] = pr_info.get("url")
                    task["_has_pr"] = True
                    task["_pr_reviews"] = pr_info.get("reviews", [])
                    task["_pr_state"] = pr_info.get("state")
                else:
                    task["_cached_pr_url"] = None
                    task["_has_pr"] = False
                    task["_pr_reviews"] = []
                    task["_pr_state"] = None

            # Sort tasks by PR status priority
            issues.sort(key=self.pr_manager.get_pr_sort_priority)

            # Return the enriched and sorted search results
            return jira_results

        except requests.exceptions.RequestException as e:
            raise JiraAPIException(f"Failed to fetch JIRA tasks: {str(e)}")
