import subprocess
from pathlib import Path
from typing import Optional


def get_repo_root() -> Path:
    """Get main repo root (works from worktrees too)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip()).resolve().parent
    except subprocess.CalledProcessError:
        return Path.cwd()


def _repo_name() -> str:
    return get_repo_root().name


def worktree_path(task_key: str) -> Path:
    return Path.home() / ".jora" / "worktrees" / _repo_name() / task_key.lower()


def _find_existing_worktree(task_key: str) -> Optional[Path]:
    """Find a worktree for this task — by directory name or branch name."""
    wt = worktree_path(task_key)
    if wt.exists():
        return wt

    branch = f"feature/{task_key.lower()}"
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    current_wt = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_wt = line[len("worktree "):]
        elif line.startswith("branch refs/heads/") and current_wt:
            if line[len("branch refs/heads/"):] == branch:
                return Path(current_wt)
    return None


def switch_to_task(task_key: str) -> Path:
    """Create or locate a worktree for the task. Returns the worktree path."""
    existing = _find_existing_worktree(task_key)
    if existing:
        return existing

    wt = worktree_path(task_key)
    branch = f"feature/{task_key.lower()}"
    wt.parent.mkdir(parents=True, exist_ok=True)

    branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        capture_output=True, text=True,
    ).returncode == 0

    # Always create from latest develop
    subprocess.run(["git", "fetch", "origin", "develop"], capture_output=True, check=True)

    if branch_exists:
        subprocess.run(["git", "worktree", "add", str(wt), branch], capture_output=True, check=True)
    else:
        subprocess.run(["git", "worktree", "add", str(wt), "-b", branch, "origin/develop"], capture_output=True, check=True)

    return wt
