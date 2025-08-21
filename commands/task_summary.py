#!/usr/bin/env python3

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
                print(f"❌ Current branch '{current_branch}' is not associated with a task.")
                print("💡 Task branches should follow the pattern: feature/TASK-KEY")
                sys.exit(1)
            
            # Fetch the specific task
            task = self.client.get_task_by_key(task_key)
            
            # Extract and display task title
            fields = task.get("fields", {})
            summary = fields.get("summary", "No summary available")
            
            print(summary)
            
        except ClientException as e:
            print(f"❌ Client Error: {str(e)}")
            sys.exit(1)
