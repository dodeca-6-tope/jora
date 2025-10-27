#!/usr/bin/env python3

import sys
from .base import BaseCommand
from exceptions import ClientException


class DeployCommand(BaseCommand):
    """Add a deploy label to the current PR."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Add a deploy label to the current PR."""
        try:
            # Ensure we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            # Check if PR exists for current branch
            if not self.client.check_pr_exists():
                print("❌ No PR found for the current branch")
                sys.exit(1)

            print("🚀 Adding deploy label to PR...")

            # Add deploy label to PR
            self.client.add_deploy_label_to_pr()

            print("✅ Deploy label added successfully to PR")

        except ClientException as e:
            print(f"❌ {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            sys.exit(1)
