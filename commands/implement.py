#!/usr/bin/env python3

import subprocess
import sys
from .base import BaseCommand
from exceptions import ClientException
from cursor_agent_utils import CursorAgentStreamHandler, run_cursor_agent
from rich.console import Console

console = Console()


class ImplementCommand(BaseCommand):
    """Guide implementation of task using cursor-agent with user approval at each step."""

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
            f"Let's work together to implement the following JIRA task:\n\n"
            f"{task_context}\n\n"
            "**WORKING APPROACH:**\n"
            "1. Study the task requirements carefully\n"
            "2. Analyze the codebase to understand relevant patterns, conventions, and architecture\n"
            "3. **BEFORE making any changes**, present your analysis and proposed approach to me\n"
            "4. Wait for my guidance and approval before proceeding\n"
            "5. Make changes incrementally based on my feedback\n"
            "6. Ask for clarification whenever requirements are unclear\n\n"
            "**CRITICAL RULES:**\n"
            "- DO NOT make any code changes without consulting me first\n"
            "- Present your plan and wait for approval before implementing\n"
            "- Show me what you intend to change and ask for confirmation\n"
            "- Work incrementally - small changes that I can review and approve\n"
            "- If you're unsure about any decision, ask me for guidance\n\n"
            "**CODE QUALITY GUIDELINES:**\n"
            "When I approve changes, follow these practices:\n"
            "- Write direct, straightforward code - no unnecessary ceremony\n"
            "- Use `const` with immediate initialization\n"
            "- Choose the simplest solution that solves the problem\n"
            "- Match existing patterns, naming conventions, and architectural decisions\n"
            "- Follow existing code style: indentation, formatting, import organization\n"
            "- Avoid over-engineering or unnecessary abstractions\n"
            "- Focus strictly on requirements - no speculative features\n"
            "- Keep changes minimal and focused\n\n"
            "**SCOPE BOUNDARIES:**\n"
            "- Focus only on files directly related to the task\n"
            "- Do NOT refactor unrelated code\n"
            "- Do NOT make changes outside the task scope\n"
            "- NEVER modify untracked or gitignored files\n\n"
            "Let's start by analyzing the task and discussing the approach together."
        )

        return prompt

    def execute(self):
        """Run cursor-agent to guide implementation based on JIRA description."""
        try:
            # Verify we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            print("🤝 Starting collaborative implementation session...\n")

            # Run implementation with guidance
            implementation_prompt = self._get_implement_task_prompt()
            exit_code = run_cursor_agent(
                implementation_prompt,
                self.handler,
                "Guided Implementation",
                auto_pilot=False,
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
