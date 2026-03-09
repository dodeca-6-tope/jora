from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests


@dataclass
class Task:
    identifier: str
    title: str
    url: str


LINEAR_API_URL = "https://api.linear.app/graphql"


class Tracker(ABC):
    """Task/issue tracker backend (Linear, Jira, etc.)."""

    @abstractmethod
    def whoami(self) -> str:
        """Return the authenticated user's display name."""

    @abstractmethod
    def fetch_tasks(self) -> list[Task]:
        """Return active tasks assigned to the current user."""


class LinearClient(Tracker):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _graphql(self, query: str) -> dict:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        resp = requests.post(
            LINEAR_API_URL, headers=headers, json={"query": query}, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            msgs = [e.get("message", str(e)) for e in data["errors"]]
            raise RuntimeError(f"Linear API error: {', '.join(msgs)}")
        return data.get("data", {})

    def whoami(self) -> str:
        return (
            self._graphql("{ viewer { name } }")
            .get("viewer", {})
            .get("name", "Unknown")
        )

    def fetch_tasks(self) -> list[Task]:
        query = """
        {
            viewer {
                assignedIssues(
                    first: 50
                    orderBy: updatedAt
                    filter: { state: { type: { nin: ["completed", "canceled"] } } }
                ) {
                    nodes { identifier title url }
                }
            }
        }
        """
        result = self._graphql(query)
        nodes = result.get("viewer", {}).get("assignedIssues", {}).get("nodes", [])
        return [
            Task(identifier=n["identifier"], title=n["title"], url=n["url"])
            for n in nodes
        ]
