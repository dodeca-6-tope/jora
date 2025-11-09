#!/usr/bin/env python3

"""
Commit Command Module

Handles committing changes with Linear task titles as commit messages.
"""

import sys
from .base import BaseCommand
from exceptions import ClientException


class CommitCommand(BaseCommand):
    """Handle commit operations with Linear task titles."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Stage all changes and commit with the Linear task title as the commit message."""
        try:
            task_title = self.client.commit_current_task()
            print(f"Committed: {task_title}")
            
        except ClientException as e:
            print(f"Error: {str(e)}")
            sys.exit(1)