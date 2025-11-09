#!/usr/bin/env python3

"""
Task Summary Command Module

Displays the task key and title for the current branch.
"""

import sys
from .base import BaseCommand
from exceptions import ClientException


class TaskSummaryCommand(BaseCommand):
    """Display the title of the task associated with the current branch."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Display the title of the task associated with the current branch."""
        try:
            # Get current branch and extract task key
            current_branch = self.client.get_current_branch()
            task_key = self.client.extract_task_key_from_branch(current_branch)
            
            if not task_key:
                print(f"Error: Branch '{current_branch}' not a task branch")
                sys.exit(1)
            
            # Fetch the specific task
            task = self.client.get_task_by_key(task_key)
            
            # Extract and display task title
            title = task.get("title", "No title available")
            
            print(f"{task_key}: {title}")
            
        except ClientException as e:
            print(f"Error: {str(e)}")
            sys.exit(1)
