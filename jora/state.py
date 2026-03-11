from dataclasses import dataclass

from jora.git import Worktree


@dataclass(frozen=True)
class TaskItem:
    id: str
    title: str
    url: str
    pr_url: str = ""
    wt: Worktree | None = None
    review_status: str = ""
    ci_status: str = ""
    session: bool = False


@dataclass(frozen=True)
class ReviewItem:
    id: str
    number: int
    title: str
    repo_slug: str = ""
    branch: str = ""
    wt: Worktree | None = None
    review_status: str = ""
    ci_status: str = ""
    session: bool = False


@dataclass(frozen=True)
class State:
    tasks: tuple[TaskItem, ...] = ()
    reviews: tuple[ReviewItem, ...] = ()
