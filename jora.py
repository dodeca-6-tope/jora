#!/usr/bin/env python3

import argparse
import sys
from clients.jira import JiraAPI
from clients.git import GitOperations
from commands.commit import CommitCommand
from commands.interactive import InteractiveCommand
from exceptions import ConfigException


def main():
    """Main function to handle Jora task management."""
    parser = argparse.ArgumentParser(description="Jora - JIRA Task Manager")
    parser.add_argument("-c", "--commit-with-title", action="store_true", 
                       help="Stage all changes and commit with the JIRA task title from the current branch")
    parser.add_argument("-i", "--interactive", action="store_true", 
                       help="Run the interactive Jora task manager")
    
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    # Initialize dependencies and validate configuration once
    try:
        jira_api = JiraAPI()
        git_ops = GitOperations()
    except ConfigException as e:
        print(f"❌ Configuration Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error during initialization: {str(e)}")
        sys.exit(1)
    
    # Create and execute appropriate command
    try:
        if args.commit_with_title:
            command = CommitCommand(jira_api, git_ops)
        elif args.interactive:
            command = InteractiveCommand(jira_api, git_ops)
        else:
            raise ValueError("No valid command found in arguments")
        
        command.execute()
    except ValueError as e:
        print(f"❌ Command Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
