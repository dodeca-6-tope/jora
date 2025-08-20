#!/usr/bin/env python3

import json
import os
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from .github import PRManager
from exceptions import JiraAPIException, ConfigException


class JiraAPI:
    """Handle all JIRA API operations."""
    
    # JIRA-specific configuration
    MAX_RESULTS = 50
    EXCLUDED_STATUSES = ["Done", "Resolved", "Closed", "Cancelled"]

    def __init__(self):
        # Load environment variables from current working directory
        current_dir = Path.cwd()
        load_dotenv(current_dir / ".env")

        self.jira_url = os.getenv("JIRA_URL")
        self.jira_email = os.getenv("JIRA_EMAIL")
        self.jira_api_key = os.getenv("JIRA_API_KEY")
        self.jira_project_key = os.getenv("JIRA_PROJECT_KEY")
        
        # Validate configuration
        self._validate_config()
        
        self.pr_manager = PRManager()

    def _validate_config(self) -> None:
        """Validate that required configuration is present."""
        if not self.jira_url:
            raise ConfigException(
                "Missing JIRA URL configuration. Please set JIRA_URL "
                "environment variable (e.g., https://yourcompany.atlassian.net)."
            )

        if not self.jira_email or not self.jira_api_key:
            raise ConfigException(
                "Missing required JIRA configuration. Please set JIRA_EMAIL and "
                "JIRA_API_KEY environment variables."
            )

        if not self.jira_project_key:
            raise ConfigException(
                "Missing JIRA project configuration. Please set JIRA_PROJECT_KEY "
                "environment variable."
            )
    
    def format_task_output(self, task: Dict) -> str:
        """
        Format a single task for console output (minimal one-line format).

        Args:
            task (dict): Task data from JIRA API

        Returns:
            str: Formatted task string
        """
        fields = task.get("fields", {})
        key = task.get("key", "Unknown")

        # Extract basic information
        summary = fields.get("summary", "No summary")
        priority = fields.get("priority", {}).get("name", "Unknown")

        # Truncate summary if too long
        max_summary_length = 55
        if len(summary) > max_summary_length:
            summary = summary[: max_summary_length - 3] + "..."

        # Create priority indicator
        priority_indicator = (
            "🔴"
            if priority in ["High", "Highest"]
            else "🟡" if priority == "Medium" else "🟢"
        )

        # Create PR status indicators (single emoji per status)
        pr_indicators = ""
        if task.get("_has_pr"):
            # Analyze reviews to determine status
            reviews = task.get("_pr_reviews", [])
            review_status = self.pr_manager.analyze_pr_reviews(reviews)

            if review_status == "APPROVED":
                pr_indicators += (
                    "✅"  # Single green check emoji for all reviews approved
                )
            elif review_status == "CHANGES_REQUESTED":
                pr_indicators += "❌"  # Single red X emoji for changes requested
            elif review_status == "REVIEW_REQUIRED":
                pr_indicators += "⏳"  # Single hourglass emoji for review required
            else:  # NO_REVIEWS
                pr_indicators += (
                    "🚀"  # Rocket emoji for PR ready to launch but no reviews
                )

        # Create the minimal one-line output
        # Place PR indicator immediately after the priority emoji.
        # Use a fixed-width placeholder when there's no PR to keep titles aligned.
        # Use two-space slot when no PR to align with emoji width on most terminals
        pr_slot = pr_indicators if pr_indicators else "  "
        output = f"{priority_indicator} {pr_slot} {key[:7]:<7} {summary}"

        return output

    def open_task_in_browser(self, task: Dict):
        """Open a JIRA task in the default web browser."""
        import webbrowser
        
        key = task.get("key", "")
        if key:
            task_url = f"{self.jira_url.rstrip('/')}/browse/{key}"
            try:
                webbrowser.open(task_url)
                print(f"\n🌐 Opening {key} in browser...")
            except Exception as e:
                print(f"\n❌ Failed to open browser: {str(e)}")
                print(f"   Manual URL: {task_url}")

    def get_project_name(self) -> str:
        """Get the project key for display purposes."""
        return self.jira_project_key

    def get_account_id_by_email(self, email: str) -> str:
        """
        Get JIRA account ID using email address.

        Args:
            email (str): Email address to search for

        Returns:
            str: The account ID for the user
        """
        # Prepare the API endpoint for user search
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/user/search"

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
            url = f"{self.jira_url.rstrip('/')}/rest/api/2/project/{project_key}/components"
            auth = (self.jira_email, self.jira_api_key)
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
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/issue"

        # Prepare authentication
        auth = (self.jira_email, self.jira_api_key)

        # Prepare headers
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Get account ID for assignment
        account_id = self.get_account_id_by_email(self.jira_email)

        # Prepare the issue data
        issue_data = {
            "fields": {
                "project": {"key": self.jira_project_key},
                "summary": task_title,
                "description": f"Task created via Jora script",
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

    def _fetch_jira_tasks_only(self) -> Dict:
        """
        Fetch only JIRA tasks without PR enrichment (for concurrent execution).
        
        Returns:
            dict: Raw JIRA search results
        """
        # Get account ID for the search
        account_id = self.get_account_id_by_email(self.jira_email)

        # Prepare the API endpoint for search
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/search"

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

        # Prepare the search data
        search_data = {
            "jql": jql,
            "maxResults": self.MAX_RESULTS,
            "fields": ["summary", "status", "priority"],
            "expand": ["changelog"],  # This might contain development info
        }

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
        url = f"{self.jira_url.rstrip('/')}/rest/api/2/issue/{task_key}"

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
            raise JiraAPIException(f"Failed to fetch task {task_key}: {str(e)}")

    def fetch_my_incomplete_tasks(self) -> Dict:
        """
        Fetch incomplete JIRA tasks assigned to the authenticated user and enrich with PR information.
        Uses concurrent fetching for better performance.

        Returns:
            dict: JIRA search results with tasks enriched with PR information
        """
        try:
            # Use ThreadPoolExecutor to fetch JIRA and GitHub data concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks concurrently
                jira_future = executor.submit(self._fetch_jira_tasks_only)
                pr_future = executor.submit(self.pr_manager.fetch_all_prs)
                
                # Wait for both to complete and get results
                try:
                    jira_results = jira_future.result(timeout=35)  # JIRA has 30s timeout + buffer
                except Exception as e:
                    raise JiraAPIException(f"Failed to fetch JIRA tasks: {str(e)}")
                
                try:
                    all_prs = pr_future.result(timeout=15)  # PR fetch timeout + buffer
                except Exception as e:
                    all_prs = []  # Continue without PR data if GitHub fails

            # Enrich each task with PR information
            issues = jira_results.get("issues", [])
            for task in issues:
                task_key = task.get("key", "")
                pr_info = self.pr_manager.find_pr_by_content(task_key, all_prs)
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
            issues.sort(key=self.pr_manager.get_pr_sort_priority)

            # Return the enriched and sorted search results
            return jira_results

        except requests.exceptions.RequestException as e:
            raise JiraAPIException(f"Failed to fetch JIRA tasks: {str(e)}")
