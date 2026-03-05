"""AI agent launcher — swap implementation to change the coding agent."""


def command(task_id: str) -> str:
    """Return the shell command to launch the agent for a given task."""
    prompt = f"Fix task {task_id}"
    escaped = prompt.replace('"', '\\"')
    return f'unset CLAUDECODE && claude "{escaped}"'
