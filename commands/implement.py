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
            "**SCOPE BOUNDARIES:**\n"
            "- Focus on files and code directly related to the task requirements\n"
            "- Apply code quality practices to: new code you write + existing code you modify\n"
            "- Do NOT refactor unrelated existing code that works fine\n"
            "- Do NOT make changes outside the scope of the task requirements\n"
            "- Keep changes focused and minimal - only what's needed for the task\n\n"
            "**CODE QUALITY:**\n"
            "- Write the most direct, straightforward code possible - no unnecessary ceremony\n"
            "- Use `const` with immediate initialization - avoid `let` declarations followed by assignment\n"
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
            "**VARIABLE USAGE (apply to code you write or modify for this task):**\n"
            "- These practices are NOT optional - write clean code from the start\n"
            "- Avoid unnecessary intermediate variables - use object properties directly\n"
            "- NEVER split variable declaration and assignment unnecessarily:\n"
            "  * ❌ BAD: `let result; result = await fetch();`\n"
            "  * ✅ GOOD: `const result = await fetch();`\n"
            "- NEVER extract object properties to single-use variables:\n"
            "  * ❌ BAD: `const result = await fn(); const buf = result.buffer; const type = result.mimeType; use(buf, type);`\n"
            "  * ✅ GOOD: `const result = await fn(); use(result.buffer, result.mimeType);`\n"
            "- NEVER declare variables outside try-catch just to use them after - move the usage INSIDE the try:\n"
            "  * ❌ BAD: `let data; try { data = await fetch(); } catch (e) { ... } use(data);`\n"
            "  * ✅ GOOD: `try { const data = await fetch(); use(data); } catch (e) { ... }`\n"
            "  * The key: if `use(data)` depends on success, it belongs at the end of the try block\n"
            "- Only extract to variables if:\n"
            "  * Used 3+ times: `const name = user.displayName; log(name); save(name); send(name);`\n"
            "  * Significantly improves readability: `const isEligible = user.age >= 18 && user.verified && !user.banned;`\n"
            "  * Avoids repeated computation: `const expensive = complexCalculation(); use1(expensive); use2(expensive);`\n\n"
            "**FUNCTION SIGNATURES:**\n"
            "- Don't make functions flexible unless flexibility is actually needed\n"
            "- If a function is only called one way, use concrete types and parameters for that use case\n"
            "- Only add optional parameters, generic types, or configuration options when:\n"
            "  * The function is already called in multiple ways in the existing code\n"
            "  * The requirements explicitly call for configurable behavior\n"
            "  * There's a clear, immediate need for flexibility\n"
            "- Avoid anticipating future needs - solve the current problem directly\n"
            "- Keep function signatures as simple and specific as possible\n\n"
            "**ERROR HANDLING & SCOPE (apply to code you write or modify for this task):**\n"
            "- CRITICAL: Success-dependent code belongs INSIDE the try block, not after the catch\n"
            "- If code should only run when the try block succeeds, put it at the END of the try block\n"
            "- This eliminates the need for intermediate `let` variables declared outside try-catch\n"
            "- Only put code after try-catch if it must run regardless of success/failure (e.g., cleanup)\n"
            "- Examples:\n"
            "  * ❌ BAD: `let result; try { result = await generate(); } catch(e) { throw e; } store.set(result);`\n"
            "  * ✅ GOOD: `try { const result = await generate(); store.set(result); } catch(e) { throw e; }`\n"
            "  * ❌ BAD: `let data; try { data = await fetch(); } catch(e) { log(e); throw e; } return process(data);`\n"
            "  * ✅ GOOD: `try { const data = await fetch(); return process(data); } catch(e) { log(e); throw e; }`\n\n"
            "**EFFICIENCY:**\n"
            "- Work incrementally - don't try to do everything at once\n"
            "- Use targeted file reads instead of reading entire large files\n"
            "- Avoid infinite loops or excessive recursion\n"
            "- If stuck, move on and note what needs manual attention\n\n"
            "**FINAL STEP - VERIFY AND COMMIT:**\n"
            "After completing the implementation:\n"
            "1. Run `yarn check` to verify everything passes\n"
            "   - If any checks fail, fix the issues before proceeding\n"
            "   - Do not commit if `yarn check` fails\n"
            "2. Stage all changes: git add -A\n"
            "3. Create a commit with a CONCISE commit message:\n"
            "   - Keep it simple and descriptive\n"
            "   - Use lowercase\n"
            "   - Under 80 characters if possible\n"
            "   - Example: 'implement user authentication flow'\n"
            "4. Confirm the commit was successful\n\n"
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
