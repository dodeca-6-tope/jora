#!/usr/bin/env python3

"""
Base Command Module

Provides the abstract base class for all Jora commands.
"""

from abc import ABC, abstractmethod


class BaseCommand(ABC):
    """Base class for all commands."""
    
    @abstractmethod
    def execute(self):
        """Execute the command. Must be implemented by subclasses."""
        pass