#!/usr/bin/env python3

from abc import ABC, abstractmethod


class BaseCommand(ABC):
    """Base class for all commands."""
    
    @abstractmethod
    def execute(self):
        """Execute the command. Must be implemented by subclasses."""
        pass