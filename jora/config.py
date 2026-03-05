from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    jora_dir: Path = Path.home() / ".jora"
    tmux_prefix: str = "jora_"

    @property
    def repos_dir(self) -> Path:
        return self.jora_dir / "repos"

    @property
    def worktrees_dir(self) -> Path:
        return self.jora_dir / "worktrees"
