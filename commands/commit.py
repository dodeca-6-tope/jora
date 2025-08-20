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
            task_title = self.client.commit_current_task()
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