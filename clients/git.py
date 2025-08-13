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

    def _validate_git_preconditions(self):
        """Validate git repository state before operations."""
        if not self.ensure_git_repo():
            raise GitOperationsException("Not in a git repository")

        if not self.check_git_status():
            raise GitOperationsException(
                "Please commit or stash changes before switching branches"
            )

    @staticmethod
    def get_feature_branch_name(task_key: str) -> str:
        """Generate feature branch name from task key."""
        return f"feature/{task_key.lower()}"

    @staticmethod
    def get_current_branch() -> str:
        """Get the name of the current git branch."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitOperationsException(f"Failed to get current branch: {str(e)}")

    @staticmethod
    def extract_task_key_from_branch(branch_name: str) -> str:
        """Extract task key from feature branch name. Returns empty string if not a feature branch."""
        if branch_name.startswith("feature/"):
            task_key = branch_name[8:]  # Remove "feature/" prefix
            return task_key.upper()
        return ""

    @staticmethod
    def stage_and_commit_with_title(task_key: str, task_title: str) -> None:
        """Stage all changes and commit with the given task title."""
        try:
            # Check if we're in a git repository
            if not GitOperations.ensure_git_repo():
                raise GitOperationsException("Not in a git repository")
            
            # Stage all changes
            subprocess.run(["git", "add", "."], check=True)
            
            # Check if there are any staged changes
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=True,
            )
            
            if not result.stdout.strip():
                raise GitOperationsException("No changes to commit")
            
            # Create commit message with just the task title
            commit_message = task_title
            
            # Commit the changes
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            
        except subprocess.CalledProcessError as e:
            raise GitOperationsException(f"Failed to stage and commit: {str(e)}")

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
    def checkout_branch(branch_name: str, create_new: bool) -> bool:
        """Checkout the branch if it exists locally; optionally create it if it doesn't exist.
        If create_new is True and branch doesn't exist, updates local develop from origin/develop 
        and creates the branch from develop. Does not perform any rebase operations."""
        try:
            # Try to checkout existing branch
            result = subprocess.run(
                ["git", "checkout", branch_name], capture_output=True
            )
            if result.returncode != 0:
                if create_new:
                    # Branch doesn't exist:
                    # 1) Update develop from origin/develop
                    GitOperations.update_develop_branch()
                    # 2) Create new branch from updated develop
                    subprocess.run(["git", "checkout", "-b", branch_name, "develop"], check=True)
                else:
                    # Branch doesn't exist and we're not allowed to create it
                    return False
            
            return True
        except subprocess.CalledProcessError:
            return False


    @staticmethod
    def has_changes_from_branch(base_branch: str = "develop") -> bool:
        """Check if current branch has changes compared to base branch. Returns True if there are changes."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_branch],
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            raise GitOperationsException(f"Failed to check for changes: {str(e)}")

    @staticmethod
    def push_branch_with_upstream(branch_name: str) -> None:
        """Push branch to origin and set upstream tracking."""
        try:
            subprocess.run(
                ["git", "push", "--set-upstream", "origin", branch_name], check=True
            )
        except subprocess.CalledProcessError as e:
            raise GitOperationsException(f"Failed to push branch: {str(e)}")

    def checkout_feature_branch(self, task: dict) -> str:
        """Checkout to the feature branch - creates if needed, checks out if exists. Does NOT rebase. Returns branch name."""
        key = task.get("key", "")
        if not key:
            raise GitOperationsException("No task key found")

        branch_name = self.get_feature_branch_name(key)

        # Validate git preconditions
        self._validate_git_preconditions()

        try:
            if not self.checkout_branch(branch_name, create_new=True):
                raise GitOperationsException("Failed to checkout feature branch")

            return branch_name

        except Exception as e:
            raise GitOperationsException(f"Failed to checkout branch: {str(e)}")


