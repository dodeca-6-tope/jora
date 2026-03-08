"""AI agent launcher — swap implementation to change the coding agent."""


def command(prompt: str) -> str:
    """Return the shell command to launch the agent with the given prompt."""
    escaped = prompt.replace('"', '\\"')
    return f'unset CLAUDECODE && claude "{escaped}"'
