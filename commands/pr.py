#!/usr/bin/env python3

"""
PR Command Module

Handles creating pull requests for Linear tasks.
"""

import sys
from .base import BaseCommand
from exceptions import ClientException


class PRCommand(BaseCommand):
    """Handle PR creation for the task associated with the current branch."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Create a PR for the task associated with the current branch."""
        try:
            # Ensure we're in a git repository
            if not self.client.ensure_git_repo():
                print("Error: Not in a git repository")
                sys.exit(1)

            # Get current branch and extract task key
            current_branch = self.client.get_current_branch()
            task_key = self.client.extract_task_key_from_branch(current_branch)
            
            if not task_key:
                print(f"Error: Branch '{current_branch}' not a task branch")
                sys.exit(1)
            
            # Fetch task details from Linear
            task = self.client.get_task_by_key(task_key)
            
            # Create the PR
            branch_name = self.client.create_new_pr(task)
            
        except ClientException as e:
            print(f"Error: {str(e)}")
            sys.exit(1)