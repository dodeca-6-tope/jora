from typing import Dict, List

import requests

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _graphql(self, query: str) -> Dict:
        headers = {"Authorization": self.api_key, "Content-Type": "application/json"}
        resp = requests.post(LINEAR_API_URL, headers=headers, json={"query": query}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            msgs = [e.get("message", str(e)) for e in data["errors"]]
            raise RuntimeError(f"Linear API error: {', '.join(msgs)}")
        return data.get("data", {})

    def whoami(self) -> str:
        result = self._graphql("{ viewer { name } }")
        return result.get("viewer", {}).get("name", "Unknown")

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

    def fetch_issue_titles(self, identifiers: List[str]) -> Dict[str, str]:
        """Fetch {identifier: title} for a list of issue identifiers."""
        if not identifiers:
            return {}
        aliases = []
        for i, ident in enumerate(identifiers):
            aliases.append(f'i{i}: issue(id: "{ident}") {{ identifier title }}')
        query = "{ " + " ".join(aliases) + " }"
        try:
            result = self._graphql(query)
            return {
                v["identifier"]: v["title"]
                for v in result.values() if v
            }
        except Exception:
            return {}
