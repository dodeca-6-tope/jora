"""Plaintext file credential get/store for non-macOS systems."""

import json
from pathlib import Path

_CREDS_FILE = Path.home() / ".jora" / "credentials"


def get(account: str) -> str:
    if not _CREDS_FILE.exists():
        return ""
    data = json.loads(_CREDS_FILE.read_text())
    return data.get(account, "")


def store(account: str, value: str):
    _CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(_CREDS_FILE.read_text()) if _CREDS_FILE.exists() else {}
    data[account] = value
    _CREDS_FILE.write_text(json.dumps(data))
    _CREDS_FILE.chmod(0o600)
