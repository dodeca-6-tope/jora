#!/usr/bin/env python3

import subprocess

from exceptions import GitOperationsException


class GitOperations:
    """Handle all Git-related operations."""

    @staticmethod
    def ensure_git_repo() -> bool:
        """Check if we're in a git repository."""
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def check_git_status() -> bool:
        """Check if there are uncommitted changes. Returns True if clean, False if dirty."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            )
            return not result.stdout.strip()
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def update_develop_branch() -> bool:
        """Update the develop branch to latest. Returns True on success."""
        try:
            subprocess.run(["git", "fetch", "origin"], check=True)
            subprocess.run(["git", "checkout", "develop"], check=True)
            subprocess.run(["git", "pull", "origin", "develop"], check=True)
            return True
        except subprocess.CalledProcessError:
            raise GitOperationsException(
                "Could not update develop branch - ensure it exists"
            )

    @staticmethod
    def switch_and_rebase_branch(branch_name: str) -> bool:
        """Switch to branch and rebase on develop. Creates branch if it doesn't exist."""
        try:
            # Try to checkout existing branch
            result = subprocess.run(
                ["git", "checkout", branch_name], capture_output=True
            )
            if result.returncode != 0:
                # Branch doesn't exist, create it from develop
                subprocess.run(["git", "checkout", "-b", branch_name], check=True)
                return True

            # Branch exists, pull latest if remote exists
            subprocess.run(["git", "pull", "origin", branch_name], capture_output=True)

            # Always rebase on develop
            subprocess.run(["git", "rebase", "develop"], check=True)
            return True
        except subprocess.CalledProcessError:
            # Return True even on rebase conflicts as user can resolve manually
            return True

    def switch_to_feature_branch(self, task: dict) -> str:
        """Smart function to switch to the feature branch - creates if needed, checks out if exists. Returns branch name."""
        key = task.get("key", "").lower()
        if not key:
            raise GitOperationsException("No task key found")

        branch_name = f"feature/{key}"

        # Basic checks
        if not self.ensure_git_repo():
            raise GitOperationsException("Not in a git repository")

        if not self.check_git_status():
            raise GitOperationsException(
                "Please commit or stash changes before switching branches"
            )

        try:
            if not self.update_develop_branch():
                raise GitOperationsException("Failed to update develop branch")

            if not self.switch_and_rebase_branch(branch_name):
                raise GitOperationsException("Failed to switch to feature branch")

            return branch_name

        except Exception as e:
            raise GitOperationsException(f"Failed to switch to branch: {str(e)}")
