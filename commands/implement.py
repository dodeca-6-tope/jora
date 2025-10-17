#!/usr/bin/env python3

import subprocess
import sys
from .base import BaseCommand
from exceptions import ClientException
from cursor_agent_utils import CursorAgentStreamHandler, run_cursor_agent
from rich.console import Console

console = Console()


class ImplementCommand(BaseCommand):
    """Implement task using cursor-agent based on JIRA task description."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client
        self.handler = CursorAgentStreamHandler()

    def _get_implement_task_prompt(self) -> str:
        """Generate prompt for implementing the task based on JIRA description."""
        # Get task context from client
        task_context = self.client.get_task_context()

        # Build prompt
        prompt = (
            f"Let's implement the following JIRA task:\n\n"
            f"{task_context}"
            "**IMPLEMENTATION APPROACH:**\n"
            "1. Study the task requirements carefully\n"
            "2. Analyze existing codebase: patterns, conventions, architecture, and style\n"
            "3. Plan your implementation to match the existing approach\n"
            "4. Implement the solution thoroughly and completely\n"
            "5. Test your changes to ensure correctness\n"
            "6. Clean up: remove unused imports, dead code, temporary files, and commented-out code\n\n"
            "**CODE QUALITY:**\n"
            "- Choose the simplest solution that solves the problem\n"
            "- Avoid over-engineering or unnecessary abstractions\n"
            "- Match existing patterns, naming conventions, and architectural decisions\n"
            "- Follow existing code style: indentation, formatting, import organization\n"
            "- Maintain type safety - avoid 'any' types or unsafe casts\n"
            "- Write self-documenting code with comments only where needed\n"
            "- Focus strictly on requirements - no speculative features\n"
            "- Leave no unused code, imports, or files behind\n"
            "- NEVER modify untracked files or gitignored files (.env, credentials, etc.)\n"
            "- Only work with tracked source code files\n\n"
            "**FUNCTION SIGNATURES:**\n"
            "- Don't make functions flexible unless flexibility is actually needed\n"
            "- If a function is only called one way, use concrete types and parameters for that use case\n"
            "- Only add optional parameters, generic types, or configuration options when:\n"
            "  * The function is already called in multiple ways in the existing code\n"
            "  * The requirements explicitly call for configurable behavior\n"
            "  * There's a clear, immediate need for flexibility\n"
            "- Avoid anticipating future needs - solve the current problem directly\n"
            "- Keep function signatures as simple and specific as possible\n\n"
            "**EFFICIENCY:**\n"
            "- Work incrementally - don't try to do everything at once\n"
            "- Use targeted file reads instead of reading entire large files\n"
            "- Avoid infinite loops or excessive recursion\n"
            "- If stuck, move on and note what needs manual attention\n\n"
            "**FINAL STEP - COMMIT:**\n"
            "After completing the implementation:\n"
            "1. Stage all changes: git add -A\n"
            "2. Create a commit with a CONCISE commit message:\n"
            "   - Keep it simple and descriptive\n"
            "   - Use lowercase\n"
            "   - Under 80 characters if possible\n"
            "   - Example: 'implement user authentication flow'\n"
            "3. Confirm the commit was successful\n\n"
            "Provide a concise summary when complete."
        )

        return prompt

    def execute(self):
        """Run cursor-agent to implement the task based on JIRA description."""
        try:
            # Verify we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            # Check for uncommitted changes
            if self.client.has_uncommitted_changes():
                print("❌ You have uncommitted changes")
                print("ℹ️  Please commit or stash your changes before running implement")
                sys.exit(1)

            print("🔨 Implementing task...\n")

            # Run implementation
            implementation_prompt = self._get_implement_task_prompt()
            exit_code = run_cursor_agent(
                implementation_prompt, self.handler, "Implementation"
            )

            if exit_code != 0:
                print("\n❌ Implementation failed")
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
