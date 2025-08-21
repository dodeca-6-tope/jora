#!/usr/bin/env python3

import sys
from .base import BaseCommand
from exceptions import ClientException


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
            
        except ClientException as e:
            print(f"❌ Client Error: {str(e)}")
            sys.exit(1)