from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Task:
    identifier: str
    title: str
    url: str


class Tracker(ABC):
    """Task/issue tracker backend (Linear, Jira, etc.)."""

    @abstractmethod
    def whoami(self) -> str:
        """Return the authenticated user's display name."""

    @abstractmethod
    def fetch_tasks(self) -> list[Task]:
        """Return active tasks assigned to the current user."""
