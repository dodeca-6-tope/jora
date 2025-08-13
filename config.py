#!/usr/bin/env python3

import os
from pathlib import Path

from dotenv import load_dotenv

from exceptions import ConfigException


class Config:
    """Configuration management for JIRA Task Manager."""

    def __init__(self):
        # Load environment variables from current working directory
        current_dir = Path.cwd()
        load_dotenv(current_dir / ".env")

        self.jira_url = os.getenv("JIRA_URL")
        self.jira_email = os.getenv("JIRA_EMAIL")
        self.jira_api_key = os.getenv("JIRA_API_KEY")
        self.jira_project_key = os.getenv("JIRA_PROJECT_KEY")

        self.max_results = 50
        self.excluded_statuses = ["Done", "Resolved", "Closed", "Cancelled"]

    def validate(self) -> None:
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
