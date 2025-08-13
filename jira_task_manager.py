#!/usr/bin/env python3

from ui_manager import UIManager


def main():
    """Main function to handle JIRA task management."""

    # Initialize UI manager and start interactive session
    ui_manager = UIManager()
    ui_manager.run_interactive_session()


if __name__ == "__main__":
    main()
