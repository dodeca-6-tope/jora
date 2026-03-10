"""macOS Keychain get/store."""

import subprocess

_SERVICE = "jora"


def get(account: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", _SERVICE, "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def store(account: str, value: str):
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s",
            _SERVICE,
            "-a",
            account,
            "-w",
            value,
            "-U",
        ],
        capture_output=True,
    )
