import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from jora.config import Config


class Git:
    def __init__(self, cfg: Config = None):
        self.cfg = cfg or Config()

    @property
    def _repos_dir(self) -> Path:
        return self.cfg.repos_dir

    @property
    def _worktrees_dir(self) -> Path:
        return self.cfg.worktrees_dir

    def add_repo(self, target: str) -> str:
        if _is_git_url(target):
            name = target.rsplit("/", 1)[-1].removesuffix(".git")
            dest = self._repos_dir / name
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
        dest = self._repos_dir / name
        if dest.exists():
            raise ValueError(f"Repo already exists: {name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(p)
        return name

    def remove_repo(self, name: str):
        dest = self._repos_dir / name
        if not dest.exists():
            raise ValueError(f"Repo not found: {name}")
        if dest.is_symlink():
            dest.unlink()
        else:
            import shutil
            shutil.rmtree(dest)

    def known_repos(self) -> List[str]:
        if not self._repos_dir.exists():
            return []
        repos = [d.name for d in self._repos_dir.iterdir() if d.is_dir()]
        wt_counts = {}
        if self._worktrees_dir.exists():
            for d in self._worktrees_dir.iterdir():
                if d.is_dir():
                    wt_counts[d.name] = sum(1 for w in d.iterdir() if w.is_dir())
        return sorted(repos, key=lambda r: (-wt_counts.get(r, 0), r))

    def repo_path(self, repo_name: str) -> Optional[Path]:
        p = self._repos_dir / repo_name
        return p if p.exists() else None

    def list_worktrees(self) -> Dict[str, Path]:
        if not self._worktrees_dir.exists():
            return {}
        result = {}
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            for wt in repo_dir.iterdir():
                if wt.is_dir() and (wt / ".git").exists():
                    result[wt.name] = wt
        return result

    def find_worktree(self, task_key: str) -> Optional[Path]:
        if not self._worktrees_dir.exists():
            return None
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            wt = repo_dir / task_key.lower()
            if wt.is_dir() and (wt / ".git").exists():
                return wt
        return None

    def is_worktree_clean(self, wt: Path) -> bool:
        cwd = str(wt)

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True,
        )
        if status.returncode != 0:
            return False
        if status.stdout.strip():
            return False

        base = _default_branch(cwd)
        unique = subprocess.run(
            ["git", "log", "--oneline", f"origin/{base}..HEAD"],
            cwd=cwd, capture_output=True, text=True,
        )
        if unique.returncode != 0:
            return False
        if not unique.stdout.strip():
            return True

        merged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{base}"],
            cwd=cwd, capture_output=True,
        )
        return merged.returncode == 0

    def clean_worktrees(self, github) -> List[str]:
        from concurrent.futures import ThreadPoolExecutor

        if not self._worktrees_dir.exists():
            return []

        all_wts = []
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            for wt in repo_dir.iterdir():
                if wt.is_dir():
                    all_wts.append((repo_dir.name, wt))

        if not all_wts:
            return []

        def fetch_repo(repo_name):
            rp = self.repo_path(repo_name)
            if rp:
                base = _default_branch(str(rp))
                subprocess.run(["git", "fetch", "origin", base], cwd=str(rp), capture_output=True)

        repo_names = {name for name, _ in all_wts}
        with ThreadPoolExecutor(max_workers=min(len(repo_names), 8)) as pool:
            list(pool.map(fetch_repo, repo_names))

        def should_clean(pair):
            repo_name, wt = pair
            rp = self.repo_path(repo_name)
            if not rp:
                return False
            if wt.name.startswith("review-"):
                return github.is_pr_merged(str(rp), wt.name.removeprefix("review-"))
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(wt), capture_output=True, text=True,
            ).stdout.strip()
            if branch and branch != "HEAD" and github.is_pr_merged(str(rp), branch):
                return True
            return self.is_worktree_clean(wt)

        with ThreadPoolExecutor(max_workers=min(len(all_wts), 8)) as pool:
            results = list(pool.map(should_clean, all_wts))

        removed = []
        for (repo_name, wt), clean in zip(all_wts, results):
            if not clean:
                continue
            removed.append(wt.name)
            self._remove_wt(repo_name, wt)

        for repo_dir in self._worktrees_dir.iterdir():
            if repo_dir.is_dir() and not any(repo_dir.iterdir()):
                repo_dir.rmdir()

        return removed

    def _remove_wt(self, repo_name: str, wt: Path):
        import shutil

        git_dir = self.repo_path(repo_name)
        if not git_dir:
            shutil.rmtree(wt, ignore_errors=True)
            return
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(wt), capture_output=True, text=True,
        ).stdout.strip()
        r = subprocess.run(
            ["git", "worktree", "remove", "--force", "--force", str(wt)],
            cwd=str(git_dir), capture_output=True,
        )
        if r.returncode != 0:
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "worktree", "prune"], cwd=str(git_dir), capture_output=True)
        if branch and branch != "HEAD":
            subprocess.run(["git", "branch", "-D", branch], cwd=str(git_dir), capture_output=True)

    def remove_worktree(self, key: str):
        wt = self.find_worktree(key)
        if not wt:
            raise ValueError(f"No worktree for {key}")
        self._remove_wt(wt.parent.name, wt)
        parent = wt.parent
        if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()

    def checkout_pr(self, pr_number: int, rp: Path) -> Path:
        key = f"review-{pr_number}"
        existing = self.find_worktree(key)
        if existing:
            return existing

        repo_name = rp.name
        wt = self._worktrees_dir / repo_name / key
        wt.parent.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            ["git", "worktree", "add", str(wt), "--detach"],
            capture_output=True, check=True, cwd=str(rp),
        )
        r = subprocess.run(
            ["gh", "pr", "checkout", str(pr_number)],
            capture_output=True, text=True, cwd=str(wt),
        )
        if r.returncode != 0:
            import shutil
            shutil.rmtree(wt, ignore_errors=True)
            subprocess.run(["git", "worktree", "prune"], capture_output=True, cwd=str(rp))
            raise RuntimeError(r.stderr.strip() or "gh pr checkout failed")
        return wt

    def switch_to_task(self, task_key: str, rp: Path) -> Path:
        existing = self.find_worktree(task_key)
        if existing:
            return existing

        repo_name = rp.name
        wt = self._worktrees_dir / repo_name / task_key.lower()
        branch = f"feature/{task_key.lower()}"
        wt.parent.mkdir(parents=True, exist_ok=True)
        cwd = str(rp)

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


def _is_git_url(s: str) -> bool:
    return s.startswith("git@") or s.startswith("https://") or s.startswith("ssh://")


def _default_branch(cwd: str) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    return "main"
