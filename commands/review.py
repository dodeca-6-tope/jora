#!/usr/bin/env python3

import subprocess
import sys
from .base import BaseCommand
from exceptions import ClientException
from cursor_agent_utils import CursorAgentStreamHandler, run_cursor_agent
from rich.console import Console

console = Console()


class ReviewCommand(BaseCommand):
    """Review implementation using cursor-agent and commit changes."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client
        self.handler = CursorAgentStreamHandler()

    def _get_review_prompt(self) -> str:
        """Generate prompt for reviewing the implementation."""
        # Get task context from client
        task_context = self.client.get_task_context()

        # Get all commits for this branch
        commits = self.client.get_all_task_commits()

        # Get overall diff for this branch
        changes = self.client.get_all_task_changes()

        # Build prompt with task context and branch information
        prompt = (
            "Let's perform a thorough code review of ALL work done on this branch.\n\n"
            f"{task_context}"
            "**BRANCH COMMITS:**\n"
            f"{commits if commits else 'No commits yet on this branch'}\n\n"
            "**ALL CHANGES ON THIS BRANCH (compared to origin/develop):**\n"
            f"```diff\n{changes if changes else 'No changes yet'}\n```\n\n"
            "**REVIEW PROCESS:**\n"
            "1. Review ALL commits listed above - understand the full implementation history\n"
            "2. Examine the complete diff of all changes on this branch\n"
            "3. Check git status to see if there are any uncommitted changes\n"
            "4. Review each modified file for:\n"
            "   - Code quality and best practices\n"
            "   - Alignment with existing codebase patterns\n"
            "   - Potential bugs or edge cases\n"
            "   - Performance concerns\n"
            "   - Security issues\n"
            "   - Test coverage (if applicable)\n"
            "   - Documentation completeness\n"
            "5. ONLY make changes if there are ACTUAL issues found\n"
            "6. Verify linter/type checker passes (if applicable)\n"
            "7. Clean up any missed unused code or imports\n\n"
            "**REVIEW CRITERIA:**\n"
            "- ✅ Does it solve the problem completely?\n"
            "- ✅ Does it follow existing patterns and conventions?\n"
            "- ✅ Is it the simplest solution that works?\n"
            "- ✅ Are there any bugs or edge cases missed?\n"
            "- ✅ Is error handling appropriate?\n"
            "- ✅ Are variable/function names clear and consistent?\n"
            "- ✅ Is the code maintainable?\n"
            "- ✅ Are there any security concerns?\n\n"
            "**CRITICAL INSTRUCTIONS:**\n"
            "- ⚠️  Do NOT make up problems that don't exist\n"
            "- ⚠️  Do NOT make unnecessary changes just to have something to commit\n"
            "- ⚠️  Do NOT add comments, formatting changes, or refactorings unless they fix actual issues\n"
            "- ⚠️  If the code is good as-is, say so and DO NOT commit anything\n"
            "- ✅ ONLY make changes if you find genuine bugs, errors, or significant issues\n\n"
            "**FINAL STEP - COMMIT (ONLY IF CHANGES WERE MADE):**\n"
            "After completing the review:\n"
            "1. Check if you made ANY changes: git status\n"
            "2. If NO changes were made:\n"
            "   - State that the review is complete and code looks good\n"
            "   - DO NOT stage or commit anything\n"
            "   - Exit successfully\n"
            "3. If changes WERE made to fix actual issues:\n"
            "   a. Run `yarn check` to verify everything passes\n"
            "      - If any checks fail, fix the issues before proceeding\n"
            "      - Do not commit if `yarn check` fails\n"
            "   b. Format touched files with prettier:\n"
            "      - Get list of modified files: git diff --name-only\n"
            "      - Run prettier on those files: npx prettier --write <file1> <file2> ...\n"
            "      - Only format files that were actually touched in this review\n"
            "   c. Stage all changes: git add -A\n"
            "   d. Create a commit with a CONCISE commit message:\n"
            "      * Start with 'review: '\n"
            "      * Add a brief summary of what was fixed (not just 'reviewed')\n"
            "      * Keep it simple and under 80 characters if possible\n"
            "      * Example: 'review: fix error handling bug'\n"
            "   e. Confirm the commit was successful\n\n"
            "Provide a concise summary of your review and any changes made (or confirm no changes were needed)."
        )

        return prompt

    def execute(self):
        """Run cursor-agent to review the implementation and commit changes."""
        try:
            # Verify we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            # Check for uncommitted changes - review should not run with uncommitted changes
            if self.client.has_uncommitted_changes():
                print("❌ You have uncommitted changes")
                print("ℹ️  Please commit or stash your changes before running review")
                sys.exit(1)

            # Check if there are any commits on this branch
            commits = self.client.get_all_task_commits()

            # Exit if there's nothing to review (no commits on this branch)
            if not commits:
                print("ℹ️  No commits to review on this branch.")
                sys.exit(0)

            # Get and display diff statistics
            stats = self.client.get_diff_stats()

            print("🔍 Reviewing all work on this branch...\n")

            # Display summary statistics
            if stats["files_changed"] > 0:
                console.print("[bold cyan]📊 Change Summary:[/bold cyan]")
                console.print(
                    f"   Files changed: [yellow]{stats['files_changed']}[/yellow]"
                )
                console.print(
                    f"   Insertions:    [green]+{stats['insertions']}[/green]"
                )
                console.print(f"   Deletions:     [red]-{stats['deletions']}[/red]")

                # Display per-file statistics
                if stats["file_list"]:
                    console.print("\n[bold cyan]📄 Files Modified:[/bold cyan]")
                    for file_stat in stats["file_list"]:
                        file = file_stat["file"]
                        added = file_stat["added"]
                        removed = file_stat["removed"]
                        console.print(
                            f"   [white]{file}[/white] ([green]+{added}[/green]/[red]-{removed}[/red])"
                        )

                print()  # Add spacing before the review starts

            # Run review
            review_prompt = self._get_review_prompt()
            exit_code = run_cursor_agent(review_prompt, self.handler, "Review Phase")

            if exit_code != 0:
                print("\n❌ Review failed")
                sys.exit(exit_code)

        except FileNotFoundError:
            print(
                "❌ Required command not found. Please ensure cursor-agent is installed and in your PATH."
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
