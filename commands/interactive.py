#!/usr/bin/env python3

import os
import sys
import time
import webbrowser
from typing import Dict, List, Optional

from .base import BaseCommand
from keyboard_utils import KeyboardInput
from exceptions import (
    JiraAPIException,
    PRManagerException,
    GitOperationsException,
)


class InteractiveCommand(BaseCommand):
    """Handle all user interface and interaction logic."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Main UI session - handles initial task fetching and interactive display."""
        print(f"🔍 Fetching your incomplete JIRA tasks...")
        print(f"   Max results: {self.client.MAX_RESULTS}")
        print()

        # Fetch tasks
        try:
            result = self.client.fetch_my_incomplete_tasks()
            issues = result.get("issues", [])
        except JiraAPIException as e:
            print(f"❌ JIRA API Error: {str(e)}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected Error during task fetching: {str(e)}")
            sys.exit(1)

        # Display interactive interface
        try:
            self.display_interactive_tasks(issues)
        except Exception as e:
            print(f"❌ Error during interactive display: {str(e)}")
            sys.exit(1)

    @staticmethod
    def clear_screen():
        """Clear the terminal screen."""
        os.system("clear" if os.name == "posix" else "cls")

    @staticmethod
    def print_header(title: str, width: int = 80):
        """Print a formatted header with title and separator."""
        print(title)
        print("-" * width)

    @staticmethod
    def display_menu_items(items: List[str], selected_index: int, prefix: str = "  "):
        """Display menu items with selection highlighting."""
        for i, item in enumerate(items):
            item_prefix = "➤ " if i == selected_index else prefix
            if i == selected_index:
                print(f"\033[7m{item_prefix}{item}\033[0m")  # Reverse video
            else:
                print(f"{item_prefix}{item}")

    @staticmethod
    def handle_arrow_navigation(key: str, current_index: int, max_items: int) -> int:
        """Handle arrow key navigation and return new index."""
        return KeyboardInput.handle_arrow_navigation(key, current_index, max_items)

    @staticmethod
    def wait_for_continue():
        """Wait for user to press Enter to continue."""
        input("\nPress Enter to continue...")

    @staticmethod
    def get_key():
        """Get a single keypress from stdin."""
        return KeyboardInput.get_key()

    @staticmethod
    def get_user_input(prompt: str) -> str:
        """Get user input for creating new tasks."""
        return KeyboardInput.get_user_input(prompt)

    def select_components_interactive(self, project_key: str) -> Optional[List[str]]:
        """Interactive component selection with arrow key navigation. Returns None if cancelled."""
        try:
            # Get available components
            available_components = self.client.get_project_components(project_key)

            if not available_components:
                print(
                    "❌ No components found in this project or unable to fetch components."
                )
                return []
        except JiraAPIException as e:
            print(f"❌ Failed to fetch components: {str(e)}")
            return []

        # Add "None" option and "Done" option
        options = (
            ["[None - No component]"]
            + available_components
            + ["[Done - Finish selection]"]
        )
        selected_components = []
        selected_index = 0

        while True:
            # Clear screen and display header
            self.clear_screen()

            self.print_header("📋 Select Components")
            print(f"Project: {project_key}")
            if selected_components:
                print(f"Selected: {', '.join(selected_components)}")
            else:
                print("Selected: None")
            self.print_header(
                "Use ↑/↓ arrow keys to navigate, Enter to toggle selection, 'q' to cancel",
                80,
            )
            print()

            # Display options with selection indicator and checkmarks
            options_with_markers = []
            for option in options:
                if option in selected_components:
                    marker = " ✓"
                elif option.startswith("[") and option.endswith("]"):
                    marker = ""  # Special options don't get checkmarks
                else:
                    marker = ""
                options_with_markers.append(f"{option}{marker}")

            self.display_menu_items(options_with_markers, selected_index)

            print()
            print("Press Enter to select/deselect, 'q' to cancel")

            # Get user input
            try:
                key = self.get_key()

                if key == "q" or key == "\x03":  # 'q' or Ctrl+C
                    print("\n❌ Component selection cancelled.")
                    return None

                selected_index = self.handle_arrow_navigation(
                    key, selected_index, len(options)
                )

                if key == "\r" or key == "\n":  # Enter
                    current_option = options[selected_index]

                    if current_option == "[None - No component]":
                        # Clear all selections and finish
                        return []
                    elif current_option == "[Done - Finish selection]":
                        # Finish selection
                        return selected_components
                    else:
                        # Toggle component selection
                        if current_option in selected_components:
                            selected_components.remove(current_option)
                        else:
                            selected_components.append(current_option)

            except KeyboardInterrupt:
                print("\n❌ Component selection cancelled.")
                return None
            except Exception as e:
                print(f"\n❌ Error reading input: {str(e)}")
                return []

    def create_new_task(self) -> Optional[Dict]:
        """Create a new JIRA task with user input."""
        # Clear screen
        self.clear_screen()
        self.print_header("📝 Create New Task")
        print()

        # Get task title from user
        task_title = self.get_user_input("Enter task title (required): ")

        if not task_title:
            print("❌ Task title is required!")
            return None

        # Interactive component selection
        print(f"\n📋 Select components for this task...")
        component_names = self.select_components_interactive(
            self.client.get_project_name()
        )

        # Check if component selection was cancelled
        if component_names is None:
            print("Task creation cancelled.")
            return None

        # Clear screen again and show final summary
        self.clear_screen()
        self.print_header("📝 Create New Task - Final Review")
        print(f"Title: {task_title}")
        print(f"Project: {self.client.get_project_name()}")
        if component_names:
            if len(component_names) == 1:
                print(f"Component: {component_names[0]}")
            else:
                print(f"Components: {', '.join(component_names)}")
        else:
            print("Components: None")
        self.print_header("", 80)

        # Create the task with proper error handling
        try:
            print(f"\n🔄 Creating task...")
            new_task = self.client.create_task(task_title, component_names)
            return new_task
        except JiraAPIException as e:
            print(f"❌ Failed to create task: {str(e)}")
            return None



    def _display_task_header(self, task: Dict):
        """Display task information header."""
        task_key = task.get("key", "Unknown")
        summary = task.get("fields", {}).get("summary", "No summary")
        pr_exists = task.get("_has_pr", False)

        self.print_header("📋 Selected Task:")
        print(f"Key: {task_key}")
        print(f"Summary: {summary}")

    def _execute_task_action(self, action_type: str, task: Dict) -> None:
        """Execute a task action."""
        task_key = task.get("key", "Unknown")

        if action_type == "browser":
            try:
                print(f"\n🌐 Opening {task_key} in browser...")
                self.client.open_task_in_browser(task_key)
            except Exception as e:
                print(f"\n❌ Failed to open browser: {str(e)}")
            self.wait_for_continue()
        elif action_type == "switch_branch":
            try:
                print("🔄 Checking out branch...")
                branch_name = self.client.switch_to_task_branch(task_key)
                print(f"✅ Checked out '{branch_name}'")
                print(f"\n🎉 Ready to work on {task_key}!")
                # Exit the tool immediately after successful checkout (clean exit)
                sys.exit(0)
            except GitOperationsException as e:
                print(f"❌ Failed to checkout branch: {str(e)}")
                self.wait_for_continue()
        elif action_type == "create_pr":
            try:
                print("🔄 Creating pull request...")
                branch_name = self.client.create_new_pr(task)
                print(f"✅ PR created successfully on branch '{branch_name}'")
                print(f"\n🎉 PR created for {task_key}!")
                # Exit the tool immediately after successful PR creation (branch is created/switched)
                sys.exit(0)
            except PRManagerException as e:
                print(f"❌ Failed to create PR: {str(e)}")
            self.wait_for_continue()
        elif action_type == "open_pr":
            pr_url = task.get("_pr_url")
            if pr_url:
                print(f"✅ Opening PR for {task_key} in browser...")
                webbrowser.open(pr_url)
                print(f"\n🎉 PR opened for {task_key}!")
            else:
                print(f"❌ No PR found for {task_key}")
            self.wait_for_continue()
        # "back" action just returns normally to exit the action menu

    def format_task_output(self, task: Dict) -> str:
        """
        Format a single task for console output (minimal one-line format).

        Args:
            task (dict): Task data from JIRA API

        Returns:
            str: Formatted task string
        """
        fields = task.get("fields", {})
        key = task.get("key", "Unknown")

        # Extract basic information
        summary = fields.get("summary", "No summary")
        priority = fields.get("priority", {}).get("name", "Unknown")

        # Truncate summary if too long
        max_summary_length = 55
        if len(summary) > max_summary_length:
            summary = summary[: max_summary_length - 3] + "..."

        # Create priority indicator
        priority_indicator = (
            "🔴"
            if priority in ["High", "Highest"]
            else "🟡" if priority == "Medium" else "🟢"
        )

        # Create PR status indicators (single emoji per status)
        pr_indicators = ""
        if task.get("_has_pr"):
            # Analyze reviews to determine status
            reviews = task.get("_pr_reviews", [])
            review_status = self.client.analyze_pr_reviews(reviews)

            if review_status == "APPROVED":
                pr_indicators += (
                    "✅"  # Single green check emoji for all reviews approved
                )
            elif review_status == "CHANGES_REQUESTED":
                pr_indicators += "❌"  # Single red X emoji for changes requested
            elif review_status == "REVIEW_REQUIRED":
                pr_indicators += "⏳"  # Single hourglass emoji for review required
            else:  # NO_REVIEWS
                pr_indicators += (
                    "🚀"  # Rocket emoji for PR ready to launch but no reviews
                )

        # Create the minimal one-line output
        # Place PR indicator immediately after the priority emoji.
        # Use a fixed-width placeholder when there's no PR to keep titles aligned.
        # Use two-space slot when no PR to align with emoji width on most terminals
        pr_slot = pr_indicators if pr_indicators else "  "
        output = f"{priority_indicator} {pr_slot} {key[:7]:<7} {summary}"

        return output

    def checkout_selected_task_branch(self, task: Dict) -> bool:
        """Handle checkout of selected task's feature branch and return success status."""
        try:
            task_key = task.get("key", "Unknown")
            print(f"\n🔄 Checking out branch for {task_key}...")
            branch_name = self.client.switch_to_task_branch(task_key)
            print(f"✅ Checked out '{branch_name}'")
            print(f"\n🎉 Ready to work on {task_key}!")
            
            # Return True to indicate successful checkout and exit
            return True
            
        except GitOperationsException as e:
            print(f"❌ Failed to checkout branch: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            return False

    def show_task_action_menu(self, task: Dict) -> None:
        """Show action menu for the selected task and handle user choice."""
        # Use cached PR information if available
        pr_exists = task.get("_has_pr", False)

        actions = [
            ("🌐 Open task in browser", "browser"),
            ("🔀 Switch to branch", "switch_branch"),
        ]

        # Add actions based on whether PR exists
        if pr_exists:
            actions.insert(0, ("🔗 Open PR", "open_pr"))
        else:
            actions.append(("📝 Create PR", "create_pr"))

        actions.append(("← Back to task list", "back"))

        selected_action = 0

        while True:
            # Clear screen and show task details
            self.clear_screen()
            self._display_task_header(task)
            print()
            print("Choose an action (use ↑/↓ to navigate, Enter to select):")

            # Display actions with selection indicator
            action_texts = [action[0] for action in actions]
            self.display_menu_items(action_texts, selected_action)

            print()
            print("Press 'q' to quit, ESC to go back")

            try:
                key_pressed = self.get_key()

                if KeyboardInput.is_quit_key(key_pressed):
                    raise KeyboardInterrupt  # Will be caught by main loop
                elif (
                    KeyboardInput.is_escape_key(key_pressed) or key_pressed == "3"
                ):  # ESC or '3' for backward compatibility
                    return  # Return to task list

                selected_action = self.handle_arrow_navigation(
                    key_pressed, selected_action, len(actions)
                )

                if KeyboardInput.is_enter_key(key_pressed):
                    _, action_type = actions[selected_action]
                    if action_type == "back":
                        return  # Exit action menu and return to task list
                    self._execute_task_action(action_type, task)
                    # Continue the action menu loop after completing the action

            except KeyboardInterrupt:
                raise  # Re-raise to be caught by main loop
            except Exception as e:
                print(f"\n❌ Error reading input: {str(e)}")
                self.wait_for_continue()
                # Continue the loop after error

    def display_interactive_tasks(self, issues: List[Dict]):
        """Display tasks with interactive keyboard navigation."""
        selected_index = 0

        while True:
            # Clear screen and display header
            self.clear_screen()

            if not issues:
                self.print_header("✨ No incomplete tasks assigned to you.")
                print("Press 'h' for help or 'n' to create a new task")
            else:
                self.print_header(
                    f"📋 Found {len(issues)} incomplete tasks (sorted by PR status):"
                )
                
                # Show cache timestamp
                cache_timestamp = self.client.get_cache_timestamp_formatted()
                if cache_timestamp:
                    print(f"📅 {cache_timestamp}")
                    print()

                # Display tasks with selection indicator
                formatted_tasks = [
                    self.format_task_output(task)
                    for task in issues
                ]
                self.display_menu_items(formatted_tasks, selected_index)

                self.print_header("", 80)
                print(f"Selected: {selected_index + 1}/{len(issues)} | Press 'h' for help")

            # Get user input
            try:
                key = self.get_key()

                if KeyboardInput.is_quit_key(key):
                    raise KeyboardInterrupt

                if KeyboardInput.is_escape_key(key):
                    raise KeyboardInterrupt  # Exit with goodbye message

                if issues:  # Only handle navigation if tasks exist
                    selected_index = self.handle_arrow_navigation(
                        key, selected_index, len(issues)
                    )

                if KeyboardInput.is_enter_key(key):
                    if issues:  # Only if tasks exist
                        selected_task = issues[selected_index]
                        # Any KeyboardInterrupt from action menu will propagate up
                        self.show_task_action_menu(selected_task)
                elif key == "n":
                    # Create new task
                    new_task = self.create_new_task()
                    if new_task:
                        print(
                            f"\n🎉 Task created successfully: {new_task.get('key', 'Unknown')}"
                        )
                        print("💡 Press 'r' to refresh the task list to see your new task")
                    self.wait_for_continue()
                elif key == "r":
                    # Refresh task list and PR information
                    print("\n🔄 Refreshing task list and PR information...")
                    try:
                        result = self.client.fetch_my_incomplete_tasks(force_refresh=True)
                        issues[:] = result.get("issues", [])  # Update the list in place
                        selected_index = 0  # Reset selection to top
                        print("✅ Task list and PR information refreshed!")
                        # Small delay to show the success message before refreshing UI
                        time.sleep(0.5)
                    except JiraAPIException as e:
                        print(f"❌ Error refreshing task list: {str(e)}")
                        self.wait_for_continue()
                elif key == "c":
                    # Checkout selected task's branch and exit
                    if issues:  # Only if tasks exist
                        selected_task = issues[selected_index]
                        checkout_success = self.checkout_selected_task_branch(selected_task)
                        if checkout_success:
                            # Clean exit after successful checkout
                            return
                        else:
                            # Only wait for input on errors
                            self.wait_for_continue()
                    else:
                        print("\n❌ No tasks available to checkout branch for")
                        self.wait_for_continue()
                elif key == "h":
                    print("\n📖 Help:")
                    print("  ↑/↓     Navigate tasks")
                    print("  Enter   Show action menu (browser/branch)")
                    print("  n       Create new task")
                    print("  c       Checkout selected task's branch and exit")
                    print("  r       Refresh task list and PR information")
                    print("  q/ESC   Quit")
                    print("  h       Show this help")
                    print("\n📋 PR Status Indicators:")
                    print("  ✅      All reviews approved")
                    print("  ❌      Changes requested by reviewers")
                    print("  ⏳      Reviews pending or mixed approval")
                    print("  🚀      PR ready to launch (no reviews yet)")
                    self.wait_for_continue()

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error reading input: {str(e)}")
                self.wait_for_continue()