import shutil
import subprocess
import time

import pytest

from jora.config import Config
from jora.git import Git
from jora.tmux import Tmux
from jora.linear import Tracker
from jora.state import State
from jora.term import Menu
from tests.mocks import FakeTracker, FakeGitHub


# -- Helpers -----------------------------------------------------------------

TEST_TMUX_PREFIX = "test_jora_"


def _wait_done(s, timeout=5):
    deadline = time.monotonic() + timeout
    while not s.done:
        if time.monotonic() > deadline:
            raise TimeoutError("load did not complete")
        time.sleep(0.01)


def _make_pr(number=1, title="", url="", branch="", reviews=None, ci=None, repo_slug="org/repo"):
    return {
        "number": number, "title": title, "url": url, "body": "",
        "headRefName": branch, "author": "", "repoSlug": repo_slug,
        "reviews": reviews or [], "statusCheckRollup": ci or [],
    }


def _make_state(tmp_path, tasks=None, prs_by_task=None, review_prs=None):
    cfg = Config(jora_dir=tmp_path, tmux_prefix=TEST_TMUX_PREFIX)
    return State(
        git=Git(cfg),
        tmux=Tmux(cfg.tmux_prefix),
        linear=FakeTracker(tasks),
        github=FakeGitHub(prs_by_task=prs_by_task, review_prs=review_prs),
        menu=Menu(),
    )


def _loaded_state(tmp_path, **kwargs):
    s = _make_state(tmp_path, **kwargs)
    s.load()
    _wait_done(s)
    return s


def _fake_worktree(tmp_path, repo_name, key):
    """Create a directory that looks like a worktree to list_worktrees."""
    wt = tmp_path / "worktrees" / repo_name / key
    wt.mkdir(parents=True)
    (wt / ".git").touch()
    return wt


def _run(cmd, **kwargs):
    subprocess.run(cmd, capture_output=True, check=True, **kwargs)


def _init_repo(tmp_path, name="myrepo"):
    """Create a bare repo + clone registered under repos/. Returns repo path."""
    bare = tmp_path / "bare" / f"{name}.git"
    bare.mkdir(parents=True)
    _run(["git", "init", "--bare"], cwd=str(bare))

    repo = tmp_path / "repos" / name
    _run(["git", "clone", str(bare), str(repo)])
    _run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(repo))
    _run(["git", "push"], cwd=str(repo))

    _run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=str(bare))

    return repo


# -- load() -----------------------------------------------------------------

def test_load_populates_tasks(tmp_path):
    # User opens jora and sees their assigned Linear tasks
    s = _loaded_state(tmp_path, tasks=[
        {"identifier": "PROJ-1", "title": "First", "url": "u1"},
        {"identifier": "PROJ-2", "title": "Second", "url": "u2"},
    ])

    rows = s.menu.sections[0].rows
    assert len(rows) == 2
    assert rows[0].title == "First"
    assert rows[1].title == "Second"


def test_load_marks_and_pr_url(tmp_path):
    # User sees review/CI status indicators next to tasks that have PRs,
    # and can open the PR URL for a task
    tasks = [
        {"identifier": "PROJ-1", "title": "Approved", "url": "u1"},
        {"identifier": "PROJ-2", "title": "No PR", "url": "u2"},
        {"identifier": "PROJ-3", "title": "Failing", "url": "u3"},
        {"identifier": "PROJ-4", "title": "Pending", "url": "u4"},
    ]
    prs = {
        "PROJ-1": [_make_pr(number=10, url="url1", branch="feature/proj-1",
                            reviews=[{"state": "APPROVED", "author": {"login": "x"}}],
                            ci=[{"conclusion": "SUCCESS"}])],
        "PROJ-3": [_make_pr(number=30, branch="feature/proj-3",
                            reviews=[{"state": "CHANGES_REQUESTED", "author": {"login": "x"}}],
                            ci=[{"conclusion": "FAILURE"}])],
        "PROJ-4": [_make_pr(number=40, branch="feature/proj-4",
                            ci=[{"conclusion": "PENDING"}])],
    }
    s = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)

    rows = s.menu.sections[0].rows
    assert rows[0].marks == ("ok", "ok")
    assert rows[1].marks == ()
    assert rows[2].marks == ("fail", "fail")
    assert rows[3].marks == ("neutral", "neutral")

    assert s.task_pr_url("PROJ-1") == "url1"
    assert s.task_pr_url("PROJ-2") is None


def test_load_task_pr_url_returns_first(tmp_path):
    # User presses 'p' to open PR — when multiple PRs match a task, the first is used
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {"PROJ-1": [
        _make_pr(number=1, url="first", branch="a"),
        _make_pr(number=2, url="second", branch="b"),
    ]}
    s = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)

    assert s.task_pr_url("PROJ-1") == "first"


def test_load_empty(tmp_path):
    # User has no assigned tasks — jora shows an empty screen
    s = _loaded_state(tmp_path)

    assert s.done
    assert s.menu.sections == []


def test_load_error_sets_message(tmp_path):
    # Linear API is down — user sees an error message instead of a crash
    class FailingTracker(Tracker):
        def whoami(self): return ""
        def fetch_tasks(self): raise RuntimeError("API down")

    cfg = Config(jora_dir=tmp_path, tmux_prefix=TEST_TMUX_PREFIX)
    s = State(
        git=Git(cfg), tmux=Tmux(cfg.tmux_prefix),
        linear=FailingTracker(), github=FakeGitHub(), menu=Menu(),
    )
    s.load()
    _wait_done(s)

    assert "API down" in s.menu.message


def test_load_sets_done(tmp_path):
    # Loading spinner shows while fetching, disappears when done
    s = _make_state(tmp_path)
    assert not s.done
    s.load()
    _wait_done(s)
    assert s.done


def test_load_detects_existing_worktrees(tmp_path):
    # User restarts jora — existing worktrees from a previous session are detected
    _fake_worktree(tmp_path, "myrepo", "proj-1")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    assert s.menu.sections[0].rows[0].worktree is True


# -- Reviews -----------------------------------------------------------------

def test_review_shown_with_worktree(tmp_path):
    # Teammate requests a review — PR appears in review section with worktree indicator
    tasks = [{"identifier": "PROJ-5", "title": "My task", "url": "u5"}]
    review_pr = _make_pr(number=99, title="[PROJ-5] change", branch="proj-5-fix")
    _fake_worktree(tmp_path, "repo", "review-99")

    s = _loaded_state(tmp_path, tasks=tasks, review_prs=[review_pr])

    assert len(s.menu.sections) == 2
    row = s.menu.sections[1].rows[0]
    assert row.title == "My task"
    assert row.worktree is True
    assert row.wt_key == "review-99"


def test_review_hidden_when_not_assigned(tmp_path):
    # PR has a ticket ID but it's not in the user's assigned tasks — hidden
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[_make_pr(number=50, title="[OTHER-9] unrelated")])

    review_sec = s.menu.sections[1]
    assert len(review_sec.rows) == 0
    assert "1 hidden" in review_sec.label


def test_review_hidden_when_no_ticket(tmp_path):
    # PR has no ticket ID in title or branch — hidden (e.g. branch named "tmp-2")
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[_make_pr(number=77, title="no ticket", branch="random")])

    review_sec = s.menu.sections[1]
    assert len(review_sec.rows) == 0
    assert "1 hidden" in review_sec.label


def test_review_section_shows_when_all_hidden(tmp_path):
    # All review PRs are hidden but the section header still shows with count
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[
                          _make_pr(number=1, title="no ticket"),
                          _make_pr(number=2, title="[OTHER-1] nope"),
                      ])

    review_sec = s.menu.sections[1]
    assert len(review_sec.rows) == 0
    assert "2 hidden" in review_sec.label


# -- refresh() ---------------------------------------------------------------

def test_refresh_tracks_worktree_lifecycle(tmp_path):
    # User creates a worktree externally, then deletes it — refresh picks up both changes
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    assert s.menu.sections[0].rows[0].worktree is False

    wt = _fake_worktree(tmp_path, "repo", "proj-1")
    s.refresh()
    assert s.menu.sections[0].rows[0].worktree is True

    shutil.rmtree(wt)
    s.refresh()
    assert s.menu.sections[0].rows[0].worktree is False


def test_refresh_preserves_data(tmp_path):
    # After refresh, PR marks and task data survive — only worktree/session flags update
    pr = _make_pr(number=42, url="pr-url", branch="feature/proj-1",
                  reviews=[{"state": "APPROVED", "author": {"login": "x"}}],
                  ci=[{"conclusion": "SUCCESS"}])
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      prs_by_task={"PROJ-1": [pr]})

    _fake_worktree(tmp_path, "repo", "proj-1")
    s.refresh()

    row = s.menu.sections[0].rows[0]
    assert row.worktree is True
    assert row.marks == ("ok", "ok")
    assert row.title == "Task"
    assert s.task_pr_url("PROJ-1") == "pr-url"


# -- Row properties ----------------------------------------------------------

def test_row_properties(tmp_path):
    # Long identifiers are truncated, worktree keys are lowercased, missing titles get fallback
    s = _loaded_state(tmp_path, tasks=[
        {"identifier": "LONGPROJ-123", "url": "u1"},
    ])

    row = s.menu.sections[0].rows[0]
    assert row.key == "LONGPROJ-"
    assert row.wt_key == "longproj-123"
    assert row.title == "No title"


# -- Section help ------------------------------------------------------------

def _row_help(s, row):
    return "  ".join(a.label for a in row.actions if a.enabled(s, row))


def test_task_row_actions(tmp_path):
    # Task row shows available actions — no session/PR so kill and PR are hidden
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    row = s.menu.sections[0].rows[0]
    help_text = _row_help(s, row)
    for label in ["open", "fix", "linear", "refresh", "clean", "quit"]:
        assert label in help_text
    assert "kill" not in help_text
    assert "PR" not in help_text


def test_task_row_actions_with_session(tmp_path):
    # Task with active session shows kill
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    s.open_task("proj-1", "myrepo")

    row = s.menu.sections[0].rows[0]
    assert "kill" in _row_help(s, row)


def test_task_row_actions_with_pr(tmp_path):
    # Task with a PR shows PR action
    pr = _make_pr(number=10, url="url1", branch="feature/proj-1")
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      prs_by_task={"PROJ-1": [pr]})

    row = s.menu.sections[0].rows[0]
    assert "PR" in _row_help(s, row)


def test_review_row_actions(tmp_path):
    # Review row shows delete instead of fix/linear
    review_pr = _make_pr(number=99, title="[PROJ-1] change")
    _fake_worktree(tmp_path, "repo", "review-99")
    s = _loaded_state(tmp_path,
                      tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[review_pr])

    row = s.menu.sections[1].rows[0]
    help_text = _row_help(s, row)
    for label in ["open", "delete", "PR", "refresh", "clean", "quit"]:
        assert label in help_text
    assert "fix" not in help_text
    assert "linear" not in help_text
    assert "kill" not in help_text


# -- open_review() -----------------------------------------------------------

def test_open_review_creates_session_for_existing_worktree(tmp_path):
    # User selects a review PR that already has a checked-out worktree — session starts
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(number=99, title="[PROJ-1] fix", branch="proj-1-fix")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[pr])

    s.open_review(pr)

    assert s.has_session("review-99")


def test_open_review_reuses_session(tmp_path):
    # User opens the same review PR twice — session is reused, not duplicated
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(number=99, title="[PROJ-1] fix", branch="proj-1-fix")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
                      review_prs=[pr])

    s.open_review(pr)
    s.open_review(pr)

    assert s.has_session("review-99")


def test_open_review_invalid_repo(tmp_path):
    # Review PR references a repo that isn't registered
    pr = _make_pr(number=99, title="[PROJ-1] fix", repo_slug="org/unknown")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    with pytest.raises(ValueError, match="not registered"):
        s.open_review(pr)


# -- open_task() -------------------------------------------------------------

def test_open_task_creates_worktree_and_session(tmp_path):
    # User selects a task for the first time — worktree is created and tmux session starts
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")
    assert s.menu.sections[0].rows[0].worktree is True
    assert s.menu.sections[0].rows[0].session is True


def test_open_task_reuses_existing_worktree(tmp_path):
    # User reopens a task after killing the session — same worktree is reused
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    wt1 = s.worktree_path("proj-1")

    s.kill_session("proj-1")
    s.open_task("proj-1", "myrepo")
    wt2 = s.worktree_path("proj-1")

    assert wt1 == wt2
    assert s.has_session("proj-1")


def test_open_task_reuses_session(tmp_path):
    # User opens the same task twice without killing — session is reused, not duplicated
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.open_task("proj-1", "myrepo")

    assert s.has_session("proj-1")


def test_open_task_invalid_repo(tmp_path):
    # User tries to open a task with a repo that isn't registered
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    with pytest.raises(ValueError, match="not registered"):
        s.open_task("proj-1", "nonexistent")


# -- fix() -------------------------------------------------------------------

def test_fix_creates_worktree_and_session(tmp_path):
    # User presses 'f' to launch AI agent on a fresh task
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.fix("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")


def test_fix_blocks_when_session_running(tmp_path):
    # User presses 'f' but a session is already open — told to attach instead
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.fix("proj-1", "myrepo")

    assert "already running" in s.menu.message


def test_fix_blocks_when_worktree_dirty(tmp_path):
    # User presses 'f' but the worktree has uncommitted changes — told to attach instead
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    wt = s.worktree_path("proj-1")
    (wt / "dirty.txt").write_text("dirty")

    s.fix("proj-1")

    assert "has changes" in s.menu.message


# -- kill_session() ----------------------------------------------------------

def test_kill_session_kills_running(tmp_path):
    # User presses 'x' to kill a running session
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    assert s.has_session("proj-1")

    s.kill_session("proj-1")
    assert not s.has_session("proj-1")
    assert "Killed" in s.menu.message


def test_kill_session_no_session(tmp_path):
    # User presses 'x' but there's no session to kill
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.kill_session("proj-1")
    assert "No session" in s.menu.message


# -- delete_worktree() -------------------------------------------------------

def test_delete_worktree_removes_worktree_and_session(tmp_path):
    # User presses 'd' on a review PR — worktree and session are both removed
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")

    s.delete_worktree("proj-1")
    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")
    assert "Removed" in s.menu.message


def test_delete_worktree_without_session(tmp_path):
    # User deletes a worktree that has no running session — worktree removed, no session error
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")
    assert s.has_worktree("proj-1")
    assert not s.has_session("proj-1")

    s.delete_worktree("proj-1")
    assert not s.has_worktree("proj-1")
    assert "Removed" in s.menu.message


def test_delete_worktree_no_worktree(tmp_path):
    # User presses 'd' but there's no worktree to delete
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.delete_worktree("proj-1")
    assert "No worktree" in s.menu.message


# -- clean() -----------------------------------------------------------------

def test_clean_removes_stale_worktrees(tmp_path):
    # User presses 'c' — worktrees with no unique commits are cleaned up
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    s.clean()
    assert not s.has_worktree("proj-1")
    assert "Removed" in s.menu.message


def test_clean_nothing_to_clean(tmp_path):
    # User presses 'c' but there are no stale worktrees
    s = _loaded_state(tmp_path)

    s.clean()
    assert "Nothing to clean" in s.menu.message


# -- Queries -----------------------------------------------------------------

def test_queries(tmp_path):
    # User checks repo registration, worktree and session status throughout a task lifecycle
    _init_repo(tmp_path, "myrepo")
    s = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    assert s.repos() == ["myrepo"]
    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")

    s.open_task("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")
