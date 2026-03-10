"""Credential access — macOS Keychain or plaintext file fallback."""

import platform
import sys

if platform.system() == "Darwin":
    from jora.creds.keychain import get, store
else:
    from jora.creds.credfile import get, store


def require(account: str, label: str) -> str:
    token = get(account)
    if not token:
        print(f"No {label} token — run: jora auth")
        sys.exit(1)
    return token


def auth(label: str, account: str, url: str, verify, reset: bool):
    existing = get(account)
    if existing and not reset:
        try:
            print(f"{label}: authenticated as {verify(existing)}")
            return
        except Exception:
            print(f"{label}: stored token is invalid — run: jora auth --reset")
            return
    token = input(f"{label} token ({url}): ").strip()
    if not token:
        print(f"{label}: skipped")
        return
    try:
        name = verify(token)
        store(account, token)
        print(f"{label}: authenticated as {name}")
    except Exception as e:
        print(f"{label}: invalid token — {e}", file=sys.stderr)
