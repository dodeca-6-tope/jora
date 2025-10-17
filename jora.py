#!/usr/bin/env python3

import argparse
import sys
from client import JoraClient
from commands.address import AddressCommand
from commands.commit import CommitCommand
from commands.implement import ImplementCommand
from commands.interactive import InteractiveCommand
from commands.pr import PRCommand
from commands.review import ReviewCommand
from commands.task_summary import TaskSummaryCommand
from exceptions import ClientException


def main():
    """Main function to handle Jora task management."""
    parser = argparse.ArgumentParser(description="Jora - JIRA Task Manager")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Browse and select from your assigned JIRA tasks",
    )
    parser.add_argument(
        "-f",
        "--implement",
        action="store_true",
        help="Implement task using AI agent based on JIRA description (requires clean working directory)",
    )
    parser.add_argument(
        "-r",
        "--review",
        action="store_true",
        help="Review all work on branch using AI agent, fix issues if found (requires clean working directory)",
    )
    parser.add_argument(
        "-a",
        "--address",
        action="store_true",
        help="Address unresolved PR comments using AI agent (requires clean working directory)",
    )
    parser.add_argument(
        "-c",
        "--commit-with-title",
        action="store_true",
        help="Stage all changes and commit with JIRA task title",
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
    if not any(vars(args).values()):
        parser.print_help()
        return

    # Initialize dependencies and validate configuration once
    try:
        client = JoraClient()
    except ClientException as e:
        print(f"❌ Configuration Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error during initialization: {str(e)}")
        sys.exit(1)

    # Create and execute appropriate command
    try:
        if args.address:
            command = AddressCommand(client)
        elif args.commit_with_title:
            command = CommitCommand(client)
        elif args.implement:
            command = ImplementCommand(client)
        elif args.interactive:
            command = InteractiveCommand(client)
        elif args.create_pr:
            command = PRCommand(client)
        elif args.review:
            command = ReviewCommand(client)
        elif args.task_summary:
            command = TaskSummaryCommand(client)
        else:
            raise ValueError("No valid command found in arguments")

        command.execute()
    except ValueError as e:
        print(f"❌ Command Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
