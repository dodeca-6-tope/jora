#!/usr/bin/env python3

import subprocess
import sys
from .base import BaseCommand
from exceptions import ClientException
from cursor_agent_utils import CursorAgentStreamHandler, run_cursor_agent


class AddressCommand(BaseCommand):
    """Address GitHub PR comments or JIRA task requirements using cursor-agent."""

    def __init__(self, client, service=None):
        """Initialize command with required dependencies."""
        self.client = client
        self.handler = CursorAgentStreamHandler()
        self.service = service  # 'github' or 'jira' (required)

    def _get_github_prompt(self) -> str:
        """Generate prompt for addressing GitHub PR comments."""
        return (
            "Let's systematically address feedback from the PR review process.\n\n"
            "**WORKFLOW:**\n"
            "1. Use 'gh pr view --json title,number,url' to identify the current PR\n"
            "2. Use 'gh api' to fetch all review comments with their resolved status\n"
            "3. Filter for UNRESOLVED comments only\n"
            "4. For each unresolved PR comment:\n"
            "   - Read and understand what change is being requested\n"
            "   - Locate the relevant code\n"
            "   - Implement the fix/improvement as requested\n"
            "   - Verify the fix works and doesn't break existing functionality\n"
            "   - Stage and commit the fix with a CONCISE commit message:\n"
            "     * Keep it simple and descriptive\n"
            "     * Use lowercase\n"
            "     * Under 80 characters if possible\n"
            "     * Example: 'fix error handling in user service'\n"
            "5. Continue until all PR feedback is addressed\n\n"
            "**CONSTRAINTS:**\n"
            "- Stay STRICTLY within PR scope - only modify files already changed in this PR\n"
            "- Do NOT make unnecessary changes beyond what's requested\n"
            "- NEVER modify untracked files or gitignored files (.env, credentials, etc.)\n"
            "- Choose the simplest solution that addresses the feedback\n"
            "- Maintain type safety - avoid 'any' types or unsafe casts\n"
            "- If a comment is unclear, implement the most reasonable interpretation\n\n"
            "Provide a concise summary when complete."
        )

    def _get_jira_prompt(self, jira_context: str) -> str:
        """Generate prompt for addressing JIRA task requirements."""
        prompt = "Let's systematically address requirements from the JIRA task.\n\n"
        if jira_context:
            prompt += f"{jira_context}\n\n"

        prompt += (
            "**WORKFLOW:**\n"
            "1. Review the JIRA task description and comments above for requirements\n"
            "2. Identify any missing functionality or requirements not yet implemented\n"
            "3. For each requirement or piece of feedback:\n"
            "   - Read and understand what change is being requested\n"
            "   - Locate the relevant code or identify where new code should be added\n"
            "   - Implement the fix/improvement as requested\n"
            "   - Verify the fix works and doesn't break existing functionality\n"
            "   - Stage and commit the fix with a CONCISE commit message:\n"
            "     * Keep it simple and descriptive\n"
            "     * Use lowercase\n"
            "     * Under 80 characters if possible\n"
            "     * Example: 'implement user validation feature'\n"
            "4. Continue until all JIRA requirements are addressed\n\n"
            "**CONSTRAINTS:**\n"
            "- Focus on implementing missing functionality based on JIRA requirements\n"
            "- Do NOT make unnecessary changes beyond what's requested\n"
            "- NEVER modify untracked files or gitignored files (.env, credentials, etc.)\n"
            "- Choose the simplest solution that addresses the requirements\n"
            "- Maintain type safety - avoid 'any' types or unsafe casts\n"
            "- Consider JIRA comments as requirements to implement, not just context\n\n"
            "Provide a concise summary when complete."
        )
        return prompt

    def execute(self):
        """Run cursor-agent to address GitHub PR comments or JIRA requirements."""
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

            if self.service == "github":
                # GitHub mode: check for PR and generate GitHub prompt
                print("🔍 Checking for existing PR...")
                pr_exists = self.client.check_pr_exists()

                if not pr_exists:
                    print("❌ No PR found for the current branch.")
                    print("ℹ️  Use 'jora -p' to create a PR first.")
                    sys.exit(1)

                print("✅ Found existing PR. Addressing GitHub PR comments...\n")
                prompt = self._get_github_prompt()
                task_description = "Addressing GitHub PR Comments"

            elif self.service == "jira":
                # JIRA mode: get JIRA context and generate JIRA prompt
                jira_context = ""
                try:
                    current_branch = self.client.get_current_branch()
                    task_key = self.client.extract_task_key_from_branch(current_branch)

                    if task_key:
                        print(f"🔍 Fetching JIRA task context for {task_key}...")
                        jira_context = self.client.get_jira_comments_context(task_key)
                        if jira_context:
                            print("✅ JIRA context loaded successfully")
                        else:
                            print("⚠️  Could not load JIRA context")
                    else:
                        print(
                            "ℹ️  No JIRA task key found in branch name - skipping JIRA context"
                        )
                except Exception as e:
                    print(f"⚠️  Could not fetch JIRA context: {str(e)}")
                    print("❌ Cannot proceed with JIRA mode without JIRA context")
                    sys.exit(1)

                prompt = self._get_jira_prompt(jira_context)
                task_description = "Addressing JIRA Requirements"
            else:
                raise ValueError(f"Unsupported service: {self.service}")

            # Run addressing
            exit_code = run_cursor_agent(prompt, self.handler, task_description)

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
