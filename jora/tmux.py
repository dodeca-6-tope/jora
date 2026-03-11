"""Tmux session lifecycle for jora tasks."""

import subprocess


class Tmux:
    def __init__(self, prefix: str = "jora_"):
        self.prefix = prefix

    def _run(self, *args: str) -> str:
        return subprocess.run(
            ["tmux", *args], capture_output=True, text=True
        ).stdout.strip()

    def session_name(self, repo: str, key: str) -> str:
        """Derive tmux session name from repo and key."""
        return f"{self.prefix}{repo}·{key}".lower().replace(":", "_")

    def has_session(self, name: str) -> bool:
        r = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
        return r.returncode == 0

    def create_session(self, name: str, cwd: str) -> None:
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", str(cwd)],
            check=True,
        )

    def attach_session(self, name: str) -> None:
        subprocess.run(["tmux", "attach-session", "-t", name])

    def send_keys(self, name: str, keys: str, enter: bool = True) -> None:
        cmd = ["tmux", "send-keys", "-t", name, keys]
        if enter:
            cmd.append("Enter")
        subprocess.run(cmd, check=True)

    def kill_session(self, name: str) -> None:
        subprocess.run(["tmux", "kill-session", "-t", name], check=True)

    def capture_pane(self, name: str) -> str:
        """Return the visible content of a tmux session's pane."""
        return self._run("capture-pane", "-t", name, "-p")

    def list_sessions(self) -> set[str]:
        out = self._run("list-sessions", "-F", "#{session_name}")
        if not out:
            return set()
        return {s for s in out.splitlines() if s.startswith(self.prefix)}
