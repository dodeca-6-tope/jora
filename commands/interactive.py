#!/usr/bin/env python3

"""
Interactive Command Module

Provides an interactive terminal UI for browsing Linear tasks, creating tasks,
and performing task-related actions (branch switching, commits, PR creation).
"""

import sys
import webbrowser
from typing import Dict, List, Optional

from .base import BaseCommand
from .commit import CommitCommand
from exceptions import ClientException
from simple_term_menu import TerminalMenu


class InteractiveCommand(BaseCommand):
    """Handle all user interface and interaction logic."""

    def __init__(self, client):
        """Initialize command with required dependencies."""
        self.client = client

    def execute(self):
        """Main UI session - shows initial menu."""
        menu_options = ["[s] Show my tasks", "[c] Create new task", "[q] Exit"]

        # Create menu once
        terminal_menu = TerminalMenu(
            menu_options,
            clear_screen=True,
            title="Jora - Linear Task Manager",
            status_bar="↑↓: Navigate | Enter: Select | Esc/q: Exit",
        )

        while True:
            choice = terminal_menu.show()

            if choice is None or choice == 2:  # Exit
                break
            elif choice == 0:  # Show tasks
                try:
                    result = self.client.fetch_my_incomplete_tasks()
                    issues = result.get("issues", [])
                    self.display_interactive_tasks(issues)
                except ClientException as e:
                    print(f"Error: {str(e)}")
                    self.wait_for_continue()
                except Exception as e:
                    print(f"Error: {str(e)}")
                    self.wait_for_continue()
            elif choice == 1:  # Create new task
                new_task = self.create_new_task()
                if new_task:
                    print(f"Created: {new_task.get('identifier')}")
                    self.wait_for_continue()

    @staticmethod
    def wait_for_continue():
        """Wait for user to press Enter to continue."""
        input("Press Enter to continue...")

    def create_new_task(self) -> Optional[Dict]:
        """Create a new Linear task with user input."""
        try:
            # State machine for wizard navigation
            step = "title"
            task_title = ""
            priority_value = None
            selected_label_ids = []
            selected_project_id = None

            # Remember cursor positions for each menu
            priority_cursor = 0
            labels_cursor = 0
            project_cursor = 0

            # Fetch labels and projects once at the beginning
            try:
                all_labels = self.client.get_team_labels()
            except ClientException as e:
                print(f"Warning: Could not fetch labels: {str(e)}")
                all_labels = []

            try:
                all_projects = self.client.get_team_projects()
            except ClientException as e:
                print(f"Warning: Could not fetch projects: {str(e)}")
                all_projects = []

            while True:
                if step == "title":
                    # Get task title from user
                    try:
                        if task_title:
                            print(f"Current: {task_title}")
                            new_title = input(
                                "Enter title (or press Enter to keep current, Ctrl+C to cancel): "
                            ).strip()
                            if new_title:
                                task_title = new_title
                        else:
                            new_title = input(
                                "Enter title (Ctrl+C to cancel): "
                            ).strip()
                            if new_title:
                                task_title = new_title

                        if not task_title:
                            print("Error: Task title is required")
                            continue
                        step = "priority"
                    except KeyboardInterrupt:
                        # Ctrl+C pressed - cancel task creation
                        return None

                elif step == "priority":
                    # Select priority
                    priority_options = [
                        "[0] Skip",
                        "[1] Urgent",
                        "[2] High",
                        "[3] Medium",
                        "[4] Low",
                    ]
                    priority_menu = TerminalMenu(
                        priority_options,
                        clear_screen=True,
                        title="Select Priority",
                        status_bar="↑↓: Navigate | Enter: Select | Esc: Back",
                        cursor_index=priority_cursor,
                    )
                    priority_idx = priority_menu.show()
                    if priority_idx is None:
                        step = "title"  # ESC -> go back to title
                        continue
                    priority_cursor = priority_idx  # Remember cursor position
                    priority_value = None if priority_idx == 0 else priority_idx
                    step = "labels"

                elif step == "labels":
                    # Select labels (multi-select)
                    if all_labels:
                        # Build preselected indices from selected_label_ids
                        preselected = (
                            tuple(
                                i
                                for i, label in enumerate(all_labels)
                                if label["id"] in selected_label_ids
                            )
                            if selected_label_ids
                            else None
                        )

                        label_menu = TerminalMenu(
                            [l["name"] for l in all_labels],
                            multi_select=True,
                            show_multi_select_hint=True,
                            multi_select_select_on_accept=False,
                            clear_screen=True,
                            title="Select Labels (press Enter when done)",
                            status_bar="↑↓: Navigate | Space: Toggle | Enter: Confirm | Esc: Back",
                            cursor_index=labels_cursor,
                            preselected_entries=preselected,
                        )
                        selected_indices = label_menu.show()
                        if selected_indices is None:
                            step = "priority"  # ESC -> go back
                            continue

                        # Normalize selection result to a list of indices
                        if isinstance(selected_indices, int):
                            indices = [selected_indices]
                        elif isinstance(selected_indices, (tuple, list)):
                            indices = list(selected_indices)
                        else:
                            indices = []

                        if indices:
                            labels_cursor = indices[0]
                            selected_label_ids = [all_labels[i]["id"] for i in indices]
                        else:
                            selected_label_ids = []
                            labels_cursor = 0
                    step = "project"

                elif step == "project":
                    # Select project
                    if all_projects:
                        project_options = ["[0] Skip"] + [
                            p["name"] for p in all_projects
                        ]
                        project_menu = TerminalMenu(
                            project_options,
                            clear_screen=True,
                            title="Select Project",
                            status_bar="↑↓: Navigate | Enter: Select | Esc: Back",
                            cursor_index=project_cursor,
                        )
                        project_idx = project_menu.show()
                        if project_idx is None:
                            step = "labels"  # ESC -> go back
                            continue
                        project_cursor = project_idx  # Remember cursor position
                        if project_idx > 0:
                            selected_project_id = all_projects[project_idx - 1]["id"]
                        else:
                            selected_project_id = None
                    step = "summary"

                elif step == "summary":
                    # Show summary and confirm
                    # Build summary display
                    summary_lines = [
                        f"Task Summary:",
                        f"  Title:    {task_title}",
                    ]

                    # Priority
                    priority_display = {
                        None: "None",
                        1: "Urgent",
                        2: "High",
                        3: "Medium",
                        4: "Low",
                    }.get(priority_value, "None")
                    summary_lines.append(f"  Priority: {priority_display}")

                    # Labels
                    if selected_label_ids and all_labels:
                        label_names = [
                            l["name"]
                            for l in all_labels
                            if l["id"] in selected_label_ids
                        ]
                        summary_lines.append(f"  Labels:   {', '.join(label_names)}")
                    else:
                        summary_lines.append(f"  Labels:   None")

                    # Project
                    if selected_project_id and all_projects:
                        project_name = next(
                            (
                                p["name"]
                                for p in all_projects
                                if p["id"] == selected_project_id
                            ),
                            "Unknown",
                        )
                        summary_lines.append(f"  Project:  {project_name}")
                    else:
                        summary_lines.append(f"  Project:  None")

                    # Show summary menu with only accept/cancel options
                    summary_options = [
                        "[v] Create Task",
                        "[x] Cancel",
                    ]

                    summary_menu = TerminalMenu(
                        summary_options,
                        clear_screen=True,
                        title="\n".join(summary_lines),
                        status_bar="↑↓: Navigate | Enter: Select | Esc: Back",
                    )

                    summary_choice = summary_menu.show()

                    if summary_choice is None:
                        step = "project"  # ESC -> go back to project
                        continue
                    elif summary_choice == 0:  # Create Task
                        step = "create"
                    elif summary_choice == 1:  # Cancel
                        return None

                elif step == "create":
                    # Create the task
                    try:
                        new_task = self.client.create_task(
                            task_title,
                            label_ids=selected_label_ids,
                            priority=priority_value,
                            project_id=selected_project_id,
                        )
                        return new_task
                    except ClientException as e:
                        print(f"Error: Failed to create task: {str(e)}")
                        self.wait_for_continue()
                        return None

        except KeyboardInterrupt:
            raise  # Propagate to execute() method

    def _execute_task_action(self, action_type: str, task: Dict) -> None:
        """Execute a task action."""
        task_key = task.get("identifier", "Unknown")

        if action_type == "browser":
            try:
                self.client.open_task_in_browser(task_key)
            except Exception as e:
                print(f"Error: {str(e)}")
            self.wait_for_continue()
        elif action_type == "switch_branch":
            try:
                branch_name = self.client.switch_to_task_branch(task_key)
                # Exit the tool immediately after successful checkout (clean exit)
                sys.exit(0)
            except ClientException as e:
                print(f"Error: {str(e)}")
                self.wait_for_continue()
        elif action_type == "commit":
            try:
                # Note: commit action works on current branch, no need to switch
                # because we want to commit changes on whatever branch the user is currently on
                commit_command = CommitCommand(self.client)
                commit_command.execute()
            except Exception:
                pass
            self.wait_for_continue()
        elif action_type == "create_pr":
            try:
                branch_name = self.client.create_new_pr(task)
                # Exit the tool immediately after successful PR creation (branch is created/switched)
                sys.exit(0)
            except ClientException as e:
                print(f"Error: {str(e)}")
            self.wait_for_continue()
        elif action_type == "open_pr":
            pr_url = task.get("_pr_url")
            if pr_url:
                webbrowser.open(pr_url)
            else:
                print(f"No PR found for {task_key}")
            self.wait_for_continue()
        # "back" action just returns normally to exit the action menu

    def format_task_output(self, task: Dict) -> str:
        """
        Format a single task for console output (minimal one-line format).

        Args:
            task (dict): Task data from Linear API

        Returns:
            str: Formatted task string
        """
        identifier = task.get("identifier", "Unknown")

        # Extract basic information
        title = task.get("title", "No title")
        priority_label = task.get("priorityLabel", "No priority")

        # Truncate title if too long
        max_title_length = 55
        if len(title) > max_title_length:
            title = title[: max_title_length - 3] + "..."

        # Create ASCII priority indicator (avoid emojis to prevent terminal glitches)
        priority_indicator = (
            "!"
            if priority_label in ["Urgent", "High"]
            else "~" if priority_label == "Medium" else "."
        )

        # Create PR status indicators (ASCII to avoid wide characters)
        pr_indicators = ""
        if task.get("_has_pr"):
            # Analyze reviews to determine status
            reviews = task.get("_pr_reviews", [])
            review_status = self.client.analyze_pr_reviews(reviews)

            if review_status == "APPROVED":
                pr_indicators += "[PR+]"
            elif review_status == "CHANGES_REQUESTED":
                pr_indicators += "[PR!]"
            elif review_status == "REVIEW_REQUIRED":
                pr_indicators += "[PR?]"
            else:  # NO_REVIEWS
                pr_indicators += "[PR ]"

        # Minimal one-line ASCII output
        pr_slot = pr_indicators if pr_indicators else ""
        output = f"{priority_indicator} {pr_slot:<5} {identifier[:9]:<9} {title}"

        return output

    def show_task_action_menu(self, task: Dict) -> None:
        """Show action menu for the selected task and handle user choice."""
        try:
            pr_exists = task.get("_has_pr", False)
            task_key = task.get("identifier", "Unknown")
            task_title = task.get("title", "No title")

            # Check current repository state
            current_has_uncommitted = self.client.has_uncommitted_changes()

            # Build action list once (it doesn't change during the loop)
            actions = []
            action_map = {}

            if pr_exists:
                actions.append("[p] Open PR")
                action_map[len(actions) - 1] = "open_pr"

            actions.append("[o] Open in browser")
            action_map[len(actions) - 1] = "browser"

            actions.append("[s] Switch to branch")
            action_map[len(actions) - 1] = "switch_branch"

            if current_has_uncommitted:
                actions.append("[c] Commit changes")
                action_map[len(actions) - 1] = "commit"

            if not pr_exists:
                actions.append("[p] Create PR")
                action_map[len(actions) - 1] = "create_pr"

            actions.append("← Back")
            action_map[len(actions) - 1] = "back"

            # Create menu once
            terminal_menu = TerminalMenu(
                actions,
                clear_screen=True,
                title=f"{task_key}: {task_title[:50]}...",
                status_bar="↑↓: Navigate | Enter: Select | Esc: Back",
            )

            while True:
                choice = terminal_menu.show()

                if choice is None or action_map.get(choice) == "back":
                    return

                try:
                    self._execute_task_action(action_map[choice], task)
                except KeyboardInterrupt:
                    raise  # Propagate to caller
                except Exception as e:
                    print(f"Error: {str(e)}")
                    self.wait_for_continue()
        except KeyboardInterrupt:
            raise  # Propagate to caller

    def display_interactive_tasks(self, issues: List[Dict]):
        """Display tasks with interactive keyboard navigation using TerminalMenu."""
        try:
            # Outer loop to handle refresh - allows staying in task menu after refresh
            while True:
                # Build task list and create menu
                if not issues:
                    # Show menu with just actions when no tasks
                    task_entries = ["[r] Refresh task list", "← Back"]
                    # Will show a message above the menu
                    menu_title = "No incomplete tasks"
                else:
                    task_entries = [self.format_task_output(task) for task in issues]
                    task_entries.append("[r] Refresh task list")
                    task_entries.append("← Back")
                    menu_title = f"My Tasks ({len(issues)})"

                terminal_menu = TerminalMenu(
                    task_entries,
                    clear_screen=True,
                    title=menu_title,
                    status_bar="↑↓: Navigate | Enter: Select | Esc: Back",
                )

                # Inner loop for menu interaction
                should_refresh = False
                while True:
                    menu_index = terminal_menu.show()

                    if menu_index is None:
                        return  # Go back to main menu

                    # Special handling when there are no tasks
                    if not issues:
                        if menu_index == 0:  # Refresh
                            should_refresh = True
                            break  # Break inner loop to refresh
                        elif menu_index == 1:  # Back
                            return
                        continue

                    # Handle action items (when there are tasks)
                    if menu_index >= len(issues):
                        action_index = menu_index - len(issues)
                        if action_index == 0:  # Refresh
                            should_refresh = True
                            break  # Break inner loop to refresh
                        elif action_index == 1:  # Back to main menu
                            return
                        continue

                    try:
                        self.show_task_action_menu(issues[menu_index])
                    except KeyboardInterrupt:
                        raise  # Propagate to execute() method
                    except Exception as e:
                        print(f"Error: {str(e)}")
                        self.wait_for_continue()

                # If we broke out of inner loop to refresh, fetch new data
                if should_refresh:
                    try:
                        result = self.client.fetch_my_incomplete_tasks(
                            force_refresh=True
                        )
                        issues = result.get("issues", [])
                        # Continue outer loop to rebuild menu with new data
                    except ClientException as e:
                        print(f"Error: {str(e)}")
                        self.wait_for_continue()
                        # Continue with current issues if refresh failed
        except KeyboardInterrupt:
            raise  # Propagate to execute() method
