#!/usr/bin/env python3

import subprocess
import sys
from .base import BaseCommand
from exceptions import ClientException
from cursor_agent_utils import CursorAgentStreamHandler, run_cursor_agent
from rich.console import Console

console = Console()


class AddressCommand(BaseCommand):
    """Address unresolved PR comments using cursor-agent."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client
        self.handler = CursorAgentStreamHandler()

    def _get_address_comments_prompt(self) -> str:
        """Generate prompt for addressing unresolved PR comments."""
        return (
            "Let's systematically address all unresolved comments for the current PR.\n\n"
            "**WORKFLOW:**\n"
            "1. Use 'gh pr view --json title,number,url' to identify the current PR\n"
            "2. Use 'gh api' to fetch all review comments with their resolved status\n"
            "3. Filter for UNRESOLVED comments only\n"
            "4. For each unresolved comment:\n"
            "   - Read and understand what change is being requested\n"
            "   - Locate the relevant code\n"
            "   - Implement the fix as requested\n"
            "   - Verify the fix works and doesn't break existing functionality\n"
            "   - Stage and commit the fix with a CONCISE commit message:\n"
            "     * Keep it simple and descriptive\n"
            "     * Use lowercase\n"
            "     * Under 80 characters if possible\n"
            "     * Example: 'fix error handling in user service'\n"
            "5. Continue until all unresolved comments are addressed\n\n"
            "**CONSTRAINTS:**\n"
            "- Stay STRICTLY within PR scope - only modify files already changed in this PR\n"
            "- Do NOT make unnecessary changes beyond what's requested\n"
            "- NEVER modify untracked files or gitignored files (.env, credentials, etc.)\n"
            "- Choose the simplest solution that addresses the feedback\n"
            "- Maintain type safety - avoid 'any' types or unsafe casts\n"
            "- If a comment is unclear, implement the most reasonable interpretation\n\n"
            "Provide a concise summary when complete."
        )

    def execute(self):
        """Run cursor-agent to address unresolved comments on the current PR."""
        try:
            # Verify we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            # Check for uncommitted changes
            if self.client.has_uncommitted_changes():
                print("❌ You have uncommitted changes")
                print("ℹ️  Please commit or stash your changes before running address")
                sys.exit(1)

            # Check if a PR exists for the current branch
            print("🔍 Checking for existing PR...")
            pr_exists = self.client.check_pr_exists()

            if not pr_exists:
                print("❌ No PR found for the current branch.")
                print("ℹ️  Use 'jora -p' to create a PR first.")
                sys.exit(1)

            print("✅ Found existing PR. Addressing unresolved comments...\n")
            prompt = self._get_address_comments_prompt()

            # Run addressing comments
            exit_code = run_cursor_agent(prompt, self.handler, "Addressing PR Comments")

            if exit_code != 0:
                sys.exit(exit_code)

        except FileNotFoundError:
            print(
                "❌ Required command not found. Please ensure cursor-agent and gh CLI are installed and in your PATH."
            )
            sys.exit(1)
        except ClientException as e:
            print(f"❌ Client Error: {str(e)}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            sys.exit(130)
        except subprocess.CalledProcessError as e:
            print(f"❌ Git command failed: {str(e)}")
            sys.exit(1)
