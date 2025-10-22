#!/usr/bin/env python3

import sys
from typing import List, Dict
from .base import BaseCommand
from exceptions import ClientException
from keyboard_utils import KeyboardInput
from rich.console import Console


class AssignCommand(BaseCommand):
    """Assign users to the current pull request with autocomplete."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client
        self.console = Console()

    def execute(self):
        """Assign users to the current pull request."""
        try:
            # Verify we're in a git repository
            if not self.client.ensure_git_repo():
                print("❌ Not in a git repository")
                sys.exit(1)

            # Check if a PR exists for the current branch
            if not self.client.check_pr_exists():
                print("❌ No PR found for the current branch.")
                print("ℹ️  Use 'jora pr' to create a PR first.")
                sys.exit(1)

            # Get repository assignees
            print("🔍 Fetching assignable users...")
            assignees = self.client.get_repository_assignees()
            if not assignees:
                print("❌ No assignable users found.")
                sys.exit(1)

            # Get and show current PR assignees
            print("🔍 Checking current assignees...")
            current_assignees = self.client.get_current_pr_assignees()

            if current_assignees:
                self.console.print(
                    f"👥 Currently assigned: {', '.join(current_assignees)}",
                    style="cyan",
                )
            else:
                print("👥 Currently assigned: None")
            print()

            # Interactive selection with autocomplete
            result = self._select_users(assignees, current_assignees)

            if result is None:  # User cancelled (ESC/quit)
                print("❌ Cancelled.")
                return

            # Handle both assign and clear with one function
            if result:
                print(f"🔄 Assigning {', '.join(result)} to PR...")
                self.client.assign_users_to_pr(result)
                self.console.print(
                    f"✅ Successfully assigned {', '.join(result)} to the PR!",
                    style="green",
                )
            elif current_assignees:  # Empty selection but had assignees = clear
                print("🔄 Clearing all assignees from PR...")
                self.client.assign_users_to_pr([])  # Empty list = clear
                self.console.print(
                    "✅ Cleared all assignees from the PR!", style="green"
                )
            else:
                print("❌ No users selected.")

        except ClientException as e:
            self.console.print(f"❌ Error: {str(e)}", style="red")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n\n⚠️  Cancelled by user")
            sys.exit(130)

    def _select_users(
        self, assignees: List[Dict], current_assignees: List[str] = None
    ) -> List[str] | None:
        """Simple autocomplete multi-select for users."""
        if current_assignees is None:
            current_assignees = []

        # Prepare user list
        users = []
        for assignee in assignees:
            username = assignee.get("login", "")
            name = assignee.get("name", "")
            if username:
                display = f"{username}" + (
                    f" ({name})" if name and name != username else ""
                )
                users.append({"username": username, "display": display})

        selected = current_assignees.copy()  # Pre-select current assignees
        search = ""
        cursor = 0

        while True:
            # Filter users by search (only show results when searching)
            if search:
                filtered = [u for u in users if search.lower() in u["display"].lower()][
                    :10
                ]
            else:
                filtered = []  # Show nothing until user starts typing

            # Adjust cursor
            if cursor >= len(filtered):
                cursor = max(0, len(filtered) - 1)

            # Display
            print("\033[2J\033[H")  # Clear screen
            self.console.print("👥 Assign Users to PR", style="bold blue")
            print("-" * 30)

            if selected:
                self.console.print(f"Selected: {', '.join(selected)}", style="green")
            else:
                print("Selected: None")
            print()

            print(f"Search: {search}_")
            print()

            if not search:
                print("💡 Start typing to search users...")
                print(f"   ({len(users)} users available)")
            elif not filtered:
                self.console.print("❌ No users found", style="red")
                print("   Try a different search")
            else:
                # Show search results
                for i, user in enumerate(filtered):
                    marker = "✓" if user["username"] in selected else " "
                    prefix = "➤" if i == cursor else " "
                    if i == cursor:
                        self.console.print(
                            f" {prefix} [{marker}] {user['display']}", style="reverse"
                        )
                    else:
                        print(f" {prefix} [{marker}] {user['display']}")

            print()
            if filtered:
                print("↑/↓ navigate • Space: toggle • Enter: done • q: quit")
            else:
                print("Type to search • Enter: done • q: quit")

            # Get input
            try:
                key = KeyboardInput.get_key()

                if key == "q" or key == "\x1b":  # q or ESC
                    return None  # Cancelled, don't change anything
                elif key in ["\r", "\n"]:  # Enter - done
                    return selected
                elif key == " ":  # Space - toggle selection
                    if filtered and cursor < len(filtered):
                        username = filtered[cursor]["username"]
                        if username in selected:
                            selected.remove(username)
                        else:
                            selected.append(username)
                elif key == "\x7f" or key == "\b":  # Backspace
                    if search:
                        search = search[:-1]
                        cursor = 0
                elif key in ["\x1b[A", "A"]:  # Up arrow
                    if filtered:
                        cursor = (cursor - 1) % len(filtered)
                elif key in ["\x1b[B", "B"]:  # Down arrow
                    if filtered:
                        cursor = (cursor + 1) % len(filtered)
                elif len(key) == 1 and key.isprintable():
                    search += key
                    cursor = 0

            except Exception:
                return None
