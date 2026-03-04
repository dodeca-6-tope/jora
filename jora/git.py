import subprocess
from pathlib import Path
from typing import Dict, List, Optional

_JORA_DIR = Path.home() / ".jora"
_REPOS_DIR = _JORA_DIR / "repos"
_WORKTREES_DIR = _JORA_DIR / "worktrees"


def _is_git_url(s: str) -> bool:
    return s.startswith("git@") or s.startswith("https://") or s.startswith("ssh://")


def add_repo(target: str) -> str:
    """Register a repo by local path (symlink) or git URL (clone). Returns the repo name."""
    if _is_git_url(target):
        name = target.rsplit("/", 1)[-1].removesuffix(".git")
        dest = _REPOS_DIR / name
        if dest.exists():
            raise ValueError(f"Repo already exists: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", target, str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise ValueError(f"Clone failed: {result.stderr.strip()}")
        return name

    p = Path(target).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"Not a directory: {p}")
    check = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(p), capture_output=True,
    )
    if check.returncode != 0:
        raise ValueError(f"Not a git repo: {p}")
    name = p.name
    dest = _REPOS_DIR / name
    if dest.exists():
        raise ValueError(f"Repo already exists: {name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(p)
    return name


def remove_repo(name: str):
    """Remove a registered repo."""
    dest = _REPOS_DIR / name
    if not dest.exists():
        raise ValueError(f"Repo not found: {name}")
    if dest.is_symlink():
        dest.unlink()
    else:
        import shutil
        shutil.rmtree(dest)


def known_repos() -> List[str]:
    """List repo names under ~/.jora/repos/."""
    if not _REPOS_DIR.exists():
        return []
    return sorted(d.name for d in _REPOS_DIR.iterdir() if d.is_dir())


def repo_path(repo_name: str) -> Optional[Path]:
    """Get the path for a registered repo."""
    p = _REPOS_DIR / repo_name
    return p if p.exists() else None


def detect_active_task() -> str:
    """If cwd is inside a jora worktree, return the task key (lowercase)."""
    cwd = Path.cwd()
    return cwd.name if str(cwd).startswith(str(_WORKTREES_DIR)) else ""


def list_worktrees() -> Dict[str, Path]:
    """Return {task_key: worktree_path} for all jora worktrees. No subprocesses."""
    if not _WORKTREES_DIR.exists():
        return {}
    result = {}
    for repo_dir in _WORKTREES_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        for wt in repo_dir.iterdir():
            if wt.is_dir() and (wt / ".git").exists():
                result[wt.name] = wt
    return result


def find_worktree(task_key: str) -> Optional[Path]:
    """Find a worktree for this task — scan all repos under ~/.jora/worktrees/."""
    if not _WORKTREES_DIR.exists():
        return None
    for repo_dir in _WORKTREES_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        wt = repo_dir / task_key.lower()
        if wt.is_dir() and (wt / ".git").exists():
            return wt
    return None


def _default_branch(cwd: str) -> str:
    """Detect the remote's default branch (e.g. main, develop)."""
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    return "main"


def _is_worktree_clean(wt: Path) -> bool:
    """A worktree is clean only if: no dirty/untracked files and no unique commits."""
    cwd = str(wt)

    # Dirty or untracked files
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd, capture_output=True, text=True,
    )
    if status.stdout.strip():
        return False

    # No unique commits beyond default branch → safe to clean
    base = _default_branch(cwd)
    unique = subprocess.run(
        ["git", "log", "--oneline", f"origin/{base}..HEAD"],
        cwd=cwd, capture_output=True, text=True,
    )
    if not unique.stdout.strip():
        return True

    # Has unique commits — only clean if branch is merged into default
    merged = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{base}"],
        cwd=cwd, capture_output=True,
    )
    return merged.returncode == 0


def clean_worktrees() -> int:
    """Remove worktrees with no dirty files and no unpushed commits. Returns count removed."""
    if not _WORKTREES_DIR.exists():
        return 0

    # Collect all worktrees
    all_wts = []
    for repo_dir in _WORKTREES_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        for wt in repo_dir.iterdir():
            if wt.is_dir():
                all_wts.append((repo_dir.name, wt))

    if not all_wts:
        return 0

    # Fetch once per repo (not per worktree)
    for repo_name in {name for name, _ in all_wts}:
        rp = repo_path(repo_name)
        if rp:
            base = _default_branch(str(rp))
            subprocess.run(["git", "fetch", "origin", base], cwd=str(rp), capture_output=True)

    # Check cleanliness in parallel
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(all_wts), 8)) as pool:
        results = list(pool.map(lambda pair: _is_worktree_clean(pair[1]), all_wts))

    # Remove clean worktrees (sequential — touches shared repo state)
    removed = 0
    for (repo_name, wt), is_clean in zip(all_wts, results):
        if not is_clean:
            continue
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(wt), capture_output=True, text=True,
        ).stdout.strip()

        git_dir = repo_path(repo_name)
        if git_dir:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt)],
                cwd=str(git_dir), capture_output=True,
            )
            base = _default_branch(str(git_dir))
            merged = subprocess.run(
                ["git", "branch", "--merged", f"origin/{base}"],
                cwd=str(git_dir), capture_output=True, text=True,
            )
            if branch in merged.stdout:
                subprocess.run(
                    ["git", "branch", "-d", branch],
                    cwd=str(git_dir), capture_output=True,
                )
        else:
            import shutil
            shutil.rmtree(wt, ignore_errors=True)
        removed += 1

    # Remove empty repo dirs under worktrees/
    for repo_dir in _WORKTREES_DIR.iterdir():
        if repo_dir.is_dir() and not any(repo_dir.iterdir()):
            repo_dir.rmdir()

    return removed


def switch_to_task(task_key: str, repo_path: Path) -> Path:
    """Create or locate a worktree for the task. Returns the worktree path."""
    existing = find_worktree(task_key)
    if existing:
        return existing

    repo_name = repo_path.name
    wt = _WORKTREES_DIR / repo_name / task_key.lower()
    branch = f"feature/{task_key.lower()}"
    wt.parent.mkdir(parents=True, exist_ok=True)
    cwd = str(repo_path)

    branch_exists = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        capture_output=True, text=True, cwd=cwd,
    ).returncode == 0

    base = _default_branch(cwd)
    subprocess.run(["git", "fetch", "origin", base], capture_output=True, check=True, cwd=cwd)

    if branch_exists:
        subprocess.run(["git", "worktree", "add", str(wt), branch], capture_output=True, check=True, cwd=cwd)
    else:
        subprocess.run(["git", "worktree", "add", str(wt), "-b", branch, f"origin/{base}"], capture_output=True, check=True, cwd=cwd)

    return wt
