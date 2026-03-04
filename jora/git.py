import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

_JORA_DIR = Path.home() / ".jora"
_WORKTREES_DIR = _JORA_DIR / "worktrees"
_REPOS_FILE = _JORA_DIR / "repos.json"


def _load_repos() -> Dict[str, str]:
    """Load {name: path} from ~/.jora/repos.json."""
    if not _REPOS_FILE.exists():
        return {}
    return json.loads(_REPOS_FILE.read_text())


def _save_repos(repos: Dict[str, str]):
    _REPOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _REPOS_FILE.write_text(json.dumps(repos, indent=2) + "\n")


def add_repo(path_str: str) -> str:
    """Register a repo by path. Returns the repo name."""
    p = Path(path_str).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"Not a directory: {p}")
    check = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(p), capture_output=True,
    )
    if check.returncode != 0:
        raise ValueError(f"Not a git repo: {p}")
    name = p.name
    repos = _load_repos()
    repos[name] = str(p)
    _save_repos(repos)
    return name


def known_repos() -> List[str]:
    """List registered repo names."""
    return sorted(_load_repos().keys())


def repo_path(repo_name: str) -> Optional[Path]:
    """Get the path for a registered repo."""
    repos = _load_repos()
    p = repos.get(repo_name)
    return Path(p) if p else None


def detect_active_task() -> str:
    """If cwd is inside a jora worktree, return the task key (lowercase)."""
    cwd = Path.cwd()
    return cwd.name if str(cwd).startswith(str(_WORKTREES_DIR)) else ""


def _find_existing_worktree(task_key: str) -> Optional[Path]:
    """Find a worktree for this task — scan all repos under ~/.jora/worktrees/."""
    if not _WORKTREES_DIR.exists():
        return None
    for repo_dir in _WORKTREES_DIR.iterdir():
        if not repo_dir.is_dir():
            continue
        wt = repo_dir / task_key.lower()
        if not wt.is_dir():
            continue
        # Verify it's a git worktree root (not a subdirectory inside another repo)
        check = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(wt), capture_output=True, text=True,
        )
        if check.returncode == 0 and Path(check.stdout.strip()) == wt:
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

    # Fetch so origin refs are up to date
    base = _default_branch(cwd)
    subprocess.run(["git", "fetch", "origin", base], cwd=cwd, capture_output=True)

    # No unique commits beyond default branch → safe to clean
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
    return removed


def switch_to_task(task_key: str, repo_path: Path) -> Path:
    """Create or locate a worktree for the task. Returns the worktree path."""
    existing = _find_existing_worktree(task_key)
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
