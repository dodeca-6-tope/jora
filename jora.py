#!/usr/bin/env python3

"""
Jora - Linear Task Manager CLI

Main entry point for the Jora command-line tool that integrates Linear task management
with Git workflows. Supports interactive task browsing, branch management, commits, and PR creation.
"""

import argparse
import sys
from client import LinearClient
from commands.commit import CommitCommand
from commands.interactive import InteractiveCommand
from commands.pr import PRCommand
from commands.task_summary import TaskSummaryCommand
from exceptions import ClientException


def main():
    """Main function to handle Linear task management."""
    parser = argparse.ArgumentParser(description="Jora - Linear Task Manager")

    # Create subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Legacy flag-based commands for backward compatibility
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Browse and select from your assigned Linear tasks",
    )
    parser.add_argument(
        "-c",
        "--commit-with-title",
        action="store_true",
        help="Stage all changes and commit with Linear task title",
    )
    parser.add_argument(
        "-p",
        "--create-pr",
        action="store_true",
        help="Create pull request for current branch with task details",
    )
    parser.add_argument(
        "-t",
        "--task-summary",
        action="store_true",
        help="Display task key and summary for current branch",
    )

    args = parser.parse_args()

    # If no arguments provided, show help
    if not any(vars(args).values()) and args.command is None:
        parser.print_help()
        return

    # Initialize dependencies and validate configuration once
    try:
        client = LinearClient()
    except ClientException as e:
        print(f"Configuration Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        sys.exit(1)

    # Create and execute appropriate command
    try:
        if args.commit_with_title:
            command = CommitCommand(client)
        elif args.interactive:
            command = InteractiveCommand(client)
        elif args.create_pr:
            command = PRCommand(client)
        elif args.task_summary:
            command = TaskSummaryCommand(client)
        else:
            raise ValueError("No valid command found in arguments")

        command.execute()
    except ValueError as e:
        print(f"Command Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
