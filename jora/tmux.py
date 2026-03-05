"""Tmux session lifecycle for jora tasks."""

import subprocess

_PREFIX = "jora_"


def _run(*args: str) -> str:
    r = subprocess.run(["tmux", *args], capture_output=True, text=True)
    return r.stdout.strip()


def has_session(name: str) -> bool:
    r = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return r.returncode == 0


def create_session(name: str, cwd: str) -> None:
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-c", str(cwd)],
        check=True,
    )


def attach_session(name: str) -> None:
    subprocess.run(["tmux", "attach-session", "-t", name])


def send_keys(name: str, keys: str, enter: bool = True) -> None:
    cmd = ["tmux", "send-keys", "-t", name, keys]
    if enter:
        cmd.append("Enter")
    subprocess.run(cmd, check=True)


def kill_session(name: str) -> None:
    subprocess.run(["tmux", "kill-session", "-t", name], check=True)


def list_sessions() -> set[str]:
    out = _run("list-sessions", "-F", "#{session_name}")
    if not out:
        return set()
    return {s for s in out.splitlines() if s.startswith(_PREFIX)}


def session_name(task_key: str) -> str:
    return f"{_PREFIX}{task_key.lower().replace(':', '_')}"
