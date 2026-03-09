import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jora.config import Config


@dataclass(frozen=True)
class Worktree:
    repo: str
    key: str


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
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ValueError(f"Clone failed: {result.stderr.strip()}")
            return name

        p = Path(target).expanduser().resolve()
        if not p.is_dir():
            raise ValueError(f"Not a directory: {p}")
        check = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(p),
            capture_output=True,
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

    def known_repos(self) -> list[str]:
        if not self._repos_dir.exists():
            return []
        repos = [d.name for d in self._repos_dir.iterdir() if d.is_dir()]
        wt_counts = {}
        if self._worktrees_dir.exists():
            for d in self._worktrees_dir.iterdir():
                if d.is_dir():
                    wt_counts[d.name] = sum(1 for w in d.iterdir() if w.is_dir())
        return sorted(repos, key=lambda r: (-wt_counts.get(r, 0), r))

    def repo_path(self, repo_name: str) -> Path | None:
        p = self._repos_dir / repo_name
        return p if p.exists() else None

    def repo_slug(self, repo_dir: str) -> str:
        try:
            r = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=repo_dir,
            )
            url = r.stdout.strip()
            if not url:
                return ""
            m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
            return m.group(1) if m else ""
        except subprocess.SubprocessError:
            return ""

    def list_worktrees(self) -> dict[Worktree, Path]:
        if not self._worktrees_dir.exists():
            return {}
        result = {}
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            for wt in repo_dir.iterdir():
                if wt.is_dir() and (wt / ".git").exists():
                    result[Worktree(repo_dir.name, wt.name)] = wt
        return result

    def find_worktree(self, wt: Worktree) -> Path | None:
        path = self._worktrees_dir / wt.repo / wt.key
        if path.is_dir() and (path / ".git").exists():
            return path
        return None

    def find_worktree_by_key(self, key: str) -> Worktree | None:
        """Scan all repos for a worktree with the given key."""
        if not self._worktrees_dir.exists():
            return None
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            wt = repo_dir / key.lower()
            if wt.is_dir() and (wt / ".git").exists():
                return Worktree(repo_dir.name, wt.name)
        return None

    def is_worktree_clean(self, wt: Worktree) -> bool:
        cwd = str(self.find_worktree(wt))

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if status.returncode != 0:
            return False
        if status.stdout.strip():
            return False

        base = _default_branch(cwd)
        unique = subprocess.run(
            ["git", "log", "--oneline", f"origin/{base}..HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if unique.returncode != 0:
            return False
        if not unique.stdout.strip():
            return True

        merged = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{base}"],
            cwd=cwd,
            capture_output=True,
        )
        return merged.returncode == 0

    def clean_worktrees(self, github) -> list[Worktree]:
        from concurrent.futures import ThreadPoolExecutor

        if not self._worktrees_dir.exists():
            return []

        all_wts = []
        for repo_dir in self._worktrees_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            for path in repo_dir.iterdir():
                if path.is_dir():
                    all_wts.append(Worktree(repo_dir.name, path.name))

        if not all_wts:
            return []

        def fetch_repo(repo_name):
            rp = self.repo_path(repo_name)
            if rp:
                base = _default_branch(str(rp))
                subprocess.run(
                    ["git", "fetch", "origin", base], cwd=str(rp), capture_output=True
                )

        repo_names = {wt.repo for wt in all_wts}
        with ThreadPoolExecutor(max_workers=min(len(repo_names), 8)) as pool:
            list(pool.map(fetch_repo, repo_names))

        def should_clean(wt):
            rp = self.repo_path(wt.repo)
            if not rp:
                return False
            path = self.find_worktree(wt)
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(path),
                capture_output=True,
                text=True,
            ).stdout.strip()
            if branch and branch != "HEAD":
                slug = self.repo_slug(str(rp))
                if github.is_branch_merged(slug, branch):
                    return True
            if wt.key.startswith("review-"):
                return False
            return self.is_worktree_clean(wt)

        with ThreadPoolExecutor(max_workers=min(len(all_wts), 8)) as pool:
            results = list(pool.map(should_clean, all_wts))

        removed = []
        for wt, clean in zip(all_wts, results):
            if clean:
                removed.append(wt)
                self._remove_wt(wt)

        for repo_dir in self._worktrees_dir.iterdir():
            if repo_dir.is_dir() and not any(repo_dir.iterdir()):
                repo_dir.rmdir()

        return removed

    def _remove_wt(self, wt: Worktree):
        import shutil

        path = self.find_worktree(wt)
        git_dir = self.repo_path(wt.repo)
        if not git_dir:
            if path:
                shutil.rmtree(path, ignore_errors=True)
            return
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
        ).stdout.strip()
        r = subprocess.run(
            ["git", "worktree", "remove", "--force", "--force", str(path)],
            cwd=str(git_dir),
            capture_output=True,
        )
        if r.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"], cwd=str(git_dir), capture_output=True
            )
        if branch and branch != "HEAD":
            subprocess.run(
                ["git", "branch", "-D", branch], cwd=str(git_dir), capture_output=True
            )

    def remove_worktree(self, wt: Worktree):
        if not self.find_worktree(wt):
            raise ValueError(f"No worktree for {wt.repo}/{wt.key}")
        self._remove_wt(wt)
        parent = self._worktrees_dir / wt.repo
        if parent.exists() and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()

    def checkout_pr(self, pr_number: int, branch: str, rp: Path) -> Worktree:
        wt = Worktree(rp.name, f"review-{pr_number}")
        existing = self.find_worktree(wt)
        if existing:
            return wt

        path = self._worktrees_dir / wt.repo / wt.key
        path.parent.mkdir(parents=True, exist_ok=True)

        r = subprocess.run(
            ["git", "fetch", "origin", f"pull/{pr_number}/head:{branch}"],
            capture_output=True,
            text=True,
            cwd=str(rp),
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "Failed to fetch PR branch")
        r = subprocess.run(
            ["git", "worktree", "add", str(path), branch],
            capture_output=True,
            text=True,
            cwd=str(rp),
        )
        if r.returncode != 0:
            import shutil

            shutil.rmtree(path, ignore_errors=True)
            subprocess.run(
                ["git", "worktree", "prune"], capture_output=True, cwd=str(rp)
            )
            raise RuntimeError(r.stderr.strip() or "Failed to checkout PR branch")
        return wt

    def switch_to_task(self, task_key: str, rp: Path) -> Worktree:
        wt = Worktree(rp.name, task_key.lower())
        existing = self.find_worktree(wt)
        if existing:
            return wt

        path = self._worktrees_dir / wt.repo / wt.key
        branch = f"feature/{task_key.lower()}"
        path.parent.mkdir(parents=True, exist_ok=True)
        cwd = str(rp)

        branch_exists = (
            subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                capture_output=True,
                text=True,
                cwd=cwd,
            ).returncode
            == 0
        )

        base = _default_branch(cwd)
        r = subprocess.run(
            ["git", "fetch", "origin", base],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "Failed to fetch from origin")

        if branch_exists:
            r = subprocess.run(
                ["git", "worktree", "add", str(path), branch],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
        else:
            r = subprocess.run(
                ["git", "worktree", "add", str(path), "-b", branch, f"origin/{base}"],
                capture_output=True,
                text=True,
                cwd=cwd,
            )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "Failed to create worktree")

        return wt


def _is_git_url(s: str) -> bool:
    return s.startswith("git@") or s.startswith("https://") or s.startswith("ssh://")


def _default_branch(cwd: str) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode == 0:
        return result.stdout.strip().removeprefix("refs/remotes/origin/")
    return "main"
