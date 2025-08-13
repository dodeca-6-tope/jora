#!/usr/bin/env python3

import sys
import termios
import tty


class KeyboardInput:
    """Utility class for handling keyboard input in terminal applications."""

    # Key constants for better readability
    ESC = "\x1b"
    ENTER = "\r"
    NEWLINE = "\n"
    CTRL_C = "\x03"
    UP_ARROW = "\x1b[A"
    DOWN_ARROW = "\x1b[B"
    RIGHT_ARROW = "\x1b[C"
    LEFT_ARROW = "\x1b[D"

    @staticmethod
    def get_key() -> str:
        """
        Get a single keypress from stdin.

        Intelligently handles escape sequences:
        - Standalone ESC key returns just '\x1b'
        - Arrow keys return full sequences like '\x1b[A'

        Returns:
            str: The key or key sequence pressed
        """
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            key = sys.stdin.read(1)

            # Handle escape sequences for arrow keys
            if key == KeyboardInput.ESC:
                # Set a short timeout to see if more characters follow
                old_settings_temp = termios.tcgetattr(fd)
                attr = termios.tcgetattr(fd)
                attr[6][termios.VMIN] = 0  # Minimum chars for non-canonical read
                attr[6][termios.VTIME] = 1  # Timeout in deciseconds (0.1 sec)
                termios.tcsetattr(fd, termios.TCSANOW, attr)

                additional = sys.stdin.read(2)
                termios.tcsetattr(fd, termios.TCSANOW, old_settings_temp)

                if additional:  # Part of escape sequence (arrow keys)
                    key += additional
                # If no additional chars, it's a pure ESC press

            return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    @staticmethod
    def is_escape_key(key: str) -> bool:
        """Check if the key is a standalone escape key press."""
        return key == KeyboardInput.ESC

    @staticmethod
    def is_enter_key(key: str) -> bool:
        """Check if the key is an enter/return key."""
        return key == KeyboardInput.ENTER or key == KeyboardInput.NEWLINE

    @staticmethod
    def is_quit_key(key: str) -> bool:
        """Check if the key is a quit command (q or Ctrl+C)."""
        return key == "q" or key == KeyboardInput.CTRL_C

    @staticmethod
    def handle_arrow_navigation(key: str, current_index: int, max_items: int) -> int:
        """
        Handle arrow key navigation and return new index.

        Args:
            key: The key pressed
            current_index: Current selected index
            max_items: Total number of items in the menu

        Returns:
            int: New index after navigation
        """
        if key == KeyboardInput.UP_ARROW:
            return (current_index - 1) % max_items
        elif key == KeyboardInput.DOWN_ARROW:
            return (current_index + 1) % max_items
        return current_index

    @staticmethod
    def get_user_input(prompt: str) -> str:
        """
        Get user input with proper terminal settings restoration.

        Args:
            prompt: The prompt to display to the user

        Returns:
            str: The user's input, stripped of whitespace
        """
        try:
            # Temporarily restore normal terminal settings for input
            old_settings = termios.tcgetattr(sys.stdin)
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

            user_input = input(prompt).strip()

            # Restore raw mode settings
            tty.setcbreak(sys.stdin.fileno())

            return user_input
        except Exception:
            return ""
