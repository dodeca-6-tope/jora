#!/usr/bin/env python3

import argparse
import sys
from client import JoraClient
from commands.commit import CommitCommand
from commands.interactive import InteractiveCommand
from commands.pr import PRCommand
from commands.task_summary import TaskSummaryCommand
from exceptions import ConfigException


def main():
    """Main function to handle Jora task management."""
    parser = argparse.ArgumentParser(description="Jora - JIRA Task Manager")
    parser.add_argument("-c", "--commit-with-title", action="store_true", 
                       help="Stage all changes and commit with the JIRA task title from the current branch")
    parser.add_argument("-i", "--interactive", action="store_true", 
                       help="Run the interactive Jora task manager")
    parser.add_argument("-p", "--create-pr", action="store_true", 
                       help="Create a pull request for the task associated with the current branch")
    parser.add_argument("-t", "--task-summary", action="store_true", 
                       help="Display the title of the task associated with the current branch")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    # Initialize dependencies and validate configuration once
    try:
        client = JoraClient()
    except ConfigException as e:
        print(f"❌ Configuration Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error during initialization: {str(e)}")
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
        print(f"❌ Command Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
