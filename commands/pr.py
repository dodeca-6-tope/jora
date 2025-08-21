#!/usr/bin/env python3

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
                print("❌ Not in a git repository")
                sys.exit(1)

            # Get current branch and extract task key
            current_branch = self.client.get_current_branch()
            task_key = self.client.extract_task_key_from_branch(current_branch)
            
            if not task_key:
                print(f"❌ Current branch '{current_branch}' does not follow the expected pattern (feature/TASK-KEY)")
                sys.exit(1)

            print(f"🔍 Found task key: {task_key}")
            
            # Fetch task details from JIRA
            print("📋 Fetching task details from JIRA...")
            task = self.client.get_task_by_key(task_key)
            task_summary = task.get("fields", {}).get("summary", "No summary")
            
            print(f"📝 Task: {task_key} - {task_summary}")
            
            # Create the PR
            print("🔄 Creating pull request...")
            branch_name = self.client.create_new_pr(task)
            
            print(f"✅ PR created successfully for {task_key}")
            print(f"🎉 Branch: {branch_name}")
            
        except ClientException as e:
            print(f"❌ Client Error: {str(e)}")
            sys.exit(1)