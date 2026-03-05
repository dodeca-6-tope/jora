import subprocess

import pytest

TEST_TMUX_PREFIX = "test_jora_"


@pytest.fixture(autouse=True)
def _cleanup_tmux():
    """Kill any test tmux sessions after each test."""
    yield
    r = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    for name in r.stdout.splitlines():
        if name.startswith(TEST_TMUX_PREFIX):
            subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
