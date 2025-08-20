#!/usr/bin/env python3

import sys
from .base import BaseCommand
from exceptions import JiraAPIException, GitOperationsException


class CommitCommand(BaseCommand):
    """Handle commit operations with JIRA task titles."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Stage all changes and commit with the JIRA task title as the commit message."""
        try:
            # Get current branch and extract task key
            current_branch = self.client.get_current_branch()
            task_key = self.client.extract_task_key_from_branch(current_branch)
            
            if not task_key:
                print(f"❌ Current branch '{current_branch}' does not follow the expected pattern (feature/TASK-KEY)")
                sys.exit(1)
            
            # Fetch task details from JIRA
            task = self.client.get_task_by_key(task_key)
            task_title = task.get("fields", {}).get("summary", "No title available")
            
            # Stage all changes and commit with task title
            self.client.stage_and_commit_with_title(task_title)
            
            print(f"✅ Committed changes with title: {task_title}")
            
        except GitOperationsException as e:
            print(f"❌ Git Error: {str(e)}")
            sys.exit(1)
        except JiraAPIException as e:
            print(f"❌ JIRA API Error: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected Error: {str(e)}")
            sys.exit(1)