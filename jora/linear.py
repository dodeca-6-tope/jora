import os
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv


LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    def __init__(self):
        from jora.git import get_repo_root
        load_dotenv(get_repo_root() / ".env")

        self.api_key = os.getenv("LINEAR_API_KEY")
        self.team_id = os.getenv("LINEAR_TEAM_ID")
        self.team_key = os.getenv("LINEAR_TEAM_KEY")

        if not self.api_key:
            raise RuntimeError("Missing LINEAR_API_KEY. Get one at https://linear.app/settings/api")

        if not self.team_id and not self.team_key:
            raise RuntimeError("Set either LINEAR_TEAM_ID (UUID) or LINEAR_TEAM_KEY (e.g. 'ENG')")

        if self.team_key and not self.team_id:
            try:
                self.team_id = self._get_team_id_by_key(self.team_key)
            except Exception:
                self.team_id = self.team_key

    def _graphql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = requests.post(LINEAR_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            msgs = [e.get("message", str(e)) for e in data["errors"]]
            raise RuntimeError(f"Linear API error: {', '.join(msgs)}")
        return data.get("data", {})

    def _get_team_id_by_key(self, team_key: str) -> str:
        result = self._graphql("{ teams { nodes { id key } } }")
        for team in result.get("teams", {}).get("nodes", []):
            if team.get("key") == team_key:
                return team["id"]
        raise RuntimeError(f"Team with key '{team_key}' not found")

    def fetch_tasks(self) -> List[Dict]:
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
        return result.get("viewer", {}).get("assignedIssues", {}).get("nodes", [])
