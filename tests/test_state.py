import shutil
import subprocess
import time
from unittest.mock import patch

import pytest

from jora.app import App, dispatch
from jora.config import Config
from jora.git import Git
from jora.github import CheckStatus, PullRequest, PullRequestReview
from jora.linear import Tracker
from jora.state import State, _noop
from jora.tmux import Tmux
from tests.mocks import FakeGitHub, FakeTracker

# -- Helpers -----------------------------------------------------------------

TEST_TMUX_PREFIX = "test_jora_"


def _wait_done(s, timeout=5):
    deadline = time.monotonic() + timeout
    while not s.done:
        if time.monotonic() > deadline:
            raise TimeoutError("load did not complete")
        time.sleep(0.01)


def _make_pr(number=1, title="", url="", branch="", reviews=None, ci=None, repo_slug="org/repo"):
    return PullRequest(
        number=number,
        title=title,
        url=url,
        body="",
        head_ref=branch,
        author_login="",
        repo_slug=repo_slug,
        reviews=reviews or [],
        checks=ci or [],
    )


def _make_state(tmp_path, tasks=None, prs_by_task=None, review_prs=None, linear=None, github=None, on_open_url=_noop):
    cfg = Config(jora_dir=tmp_path, tmux_prefix=TEST_TMUX_PREFIX)
    alerts = []
    app = App()
    s = State(
        git=Git(cfg),
        tmux=Tmux(cfg.tmux_prefix),
        linear=linear or FakeTracker(tasks),
        github=github or FakeGitHub(prs_by_task=prs_by_task, review_prs=review_prs),
        on_alert=lambda text: alerts.append(text),
        on_open_url=on_open_url,
        on_change=lambda: app.rebuild(),
    )
    app.state = s
    return s, alerts, app


def _loaded_state(tmp_path, **kwargs):
    s, alerts, app = _make_state(tmp_path, **kwargs)
    s.load()
    _wait_done(s)
    return s, alerts, app


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


def _task_row(app, idx=0):
    return app.sections[0].rows[idx]


def _wait_loading(s, timeout=5):
    """Wait for background work to finish."""
    deadline = time.monotonic() + timeout
    while s.loading:
        if time.monotonic() > deadline:
            raise TimeoutError("loading did not complete")
        time.sleep(0.01)


# -- load() -----------------------------------------------------------------


def test_load_populates_tasks(tmp_path):
    # User opens jora and sees their assigned Linear tasks
    s, _, app = _loaded_state(
        tmp_path,
        tasks=[
            {"identifier": "PROJ-1", "title": "First", "url": "u1"},
            {"identifier": "PROJ-2", "title": "Second", "url": "u2"},
        ],
    )

    rows = app.sections[0].rows
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
        "PROJ-1": [
            _make_pr(
                number=10,
                url="url1",
                branch="feature/proj-1",
                reviews=[PullRequestReview("APPROVED", "x")],
                ci=[CheckStatus("SUCCESS")],
            )
        ],
        "PROJ-3": [
            _make_pr(
                number=30,
                branch="feature/proj-3",
                reviews=[PullRequestReview("CHANGES_REQUESTED", "x")],
                ci=[CheckStatus("FAILURE")],
            )
        ],
        "PROJ-4": [_make_pr(number=40, branch="feature/proj-4", ci=[CheckStatus("PENDING")])],
    }
    s, _, app = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)

    rows = app.sections[0].rows
    assert rows[0].marks == ("ok", "ok")
    assert rows[1].marks == ()
    assert rows[2].marks == ("fail", "fail")
    assert rows[3].marks == ("neutral", "neutral")

    assert s.task_pr_url("PROJ-1") == "url1"
    assert s.task_pr_url("PROJ-2") is None


def test_load_marks_mixed_reviewers(tmp_path):
    # One reviewer approved, another requested changes — changes_requested wins
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {
        "PROJ-1": [
            _make_pr(
                number=1,
                branch="proj-1",
                reviews=[
                    PullRequestReview("APPROVED", "alice"),
                    PullRequestReview("CHANGES_REQUESTED", "bob"),
                ],
                ci=[CheckStatus("SUCCESS")],
            )
        ]
    }
    _, _, app = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)
    assert app.sections[0].rows[0].marks == ("fail", "ok")


def test_load_marks_review_ok_ci_fail(tmp_path):
    # PR is approved but CI is failing
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {
        "PROJ-1": [
            _make_pr(
                number=1,
                branch="proj-1",
                reviews=[PullRequestReview("APPROVED", "alice")],
                ci=[CheckStatus("SUCCESS"), CheckStatus("FAILURE")],
            )
        ]
    }
    _, _, app = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)
    assert app.sections[0].rows[0].marks == ("ok", "fail")


def test_load_marks_no_ci(tmp_path):
    # PR has reviews but no CI checks at all
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {
        "PROJ-1": [
            _make_pr(
                number=1,
                branch="proj-1",
                reviews=[PullRequestReview("APPROVED", "alice")],
            )
        ]
    }
    _, _, app = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)
    assert app.sections[0].rows[0].marks == ("ok", "neutral")


def test_load_marks_reviewer_updates_verdict(tmp_path):
    # Same reviewer first requests changes, then approves — latest wins
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {
        "PROJ-1": [
            _make_pr(
                number=1,
                branch="proj-1",
                reviews=[
                    PullRequestReview("CHANGES_REQUESTED", "alice"),
                    PullRequestReview("APPROVED", "alice"),
                ],
                ci=[CheckStatus("SUCCESS")],
            )
        ]
    }
    _, _, app = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)
    assert app.sections[0].rows[0].marks == ("ok", "ok")


def test_load_task_pr_url_returns_first(tmp_path):
    # User presses 'p' to open PR — when multiple PRs match a task, the first is used
    tasks = [{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    prs = {
        "PROJ-1": [
            _make_pr(number=1, url="first", branch="a"),
            _make_pr(number=2, url="second", branch="b"),
        ]
    }
    s, _, _ = _loaded_state(tmp_path, tasks=tasks, prs_by_task=prs)

    assert s.task_pr_url("PROJ-1") == "first"


def test_load_empty(tmp_path):
    # User has no assigned tasks — jora shows an empty tasks section
    s, _, app = _loaded_state(tmp_path)

    assert s.done
    assert len(app.sections) == 1
    assert app.sections[0].rows == []


def test_load_error_sets_message(tmp_path):
    # Linear API is down — user sees an error message instead of a crash
    class FailingTracker(Tracker):
        def whoami(self):
            return ""

        def fetch_tasks(self):
            raise RuntimeError("API down")

    _, alerts, _ = _loaded_state(tmp_path, linear=FailingTracker())

    assert "API down" in " ".join(alerts)


def test_load_sets_done(tmp_path):
    # Loading spinner shows while fetching, disappears when done
    s, _, _ = _make_state(tmp_path)
    assert not s.done
    s.load()
    _wait_done(s)
    assert s.done


def test_load_detects_existing_worktrees(tmp_path):
    # User restarts jora — existing worktrees from a previous session are detected
    _fake_worktree(tmp_path, "myrepo", "proj-1")
    _, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    assert app.sections[0].rows[0].worktree is True


# -- Reviews -----------------------------------------------------------------


def test_review_shown_with_worktree(tmp_path):
    # Teammate requests a review — PR appears in review tab with worktree indicator
    review_pr = _make_pr(number=99, title="[PROJ-5] change", branch="proj-5-fix")
    _fake_worktree(tmp_path, "repo", "review-99")

    _, _, app = _loaded_state(tmp_path, review_prs=[review_pr])
    app.next_tab()

    assert len(app.sections) == 1
    row = app.sections[0].rows[0]
    assert row.key == "99"
    assert row.title == "[PROJ-5] change"
    assert row.worktree is True
    assert row.wt_key == "review-99"


def test_review_shows_pr_title(tmp_path):
    # All review PRs show with their number and title
    _, _, app = _loaded_state(tmp_path, review_prs=[_make_pr(number=77, title="fix typo", branch="random")])
    app.next_tab()

    row = app.sections[0].rows[0]
    assert row.title == "fix typo"
    assert row.key == "77"


# -- rebuild ---------------------------------------------------------------


def test_rebuild_tracks_worktree_lifecycle(tmp_path):
    # User creates a worktree externally, then deletes it — rebuild picks up both changes
    _, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    assert app.sections[0].rows[0].worktree is False

    wt = _fake_worktree(tmp_path, "repo", "proj-1")
    app.rebuild()
    assert app.sections[0].rows[0].worktree is True

    shutil.rmtree(wt)
    app.rebuild()
    assert app.sections[0].rows[0].worktree is False


def test_rebuild_preserves_data(tmp_path):
    # After rebuild, PR marks and task data survive — only worktree/session flags update
    pr = _make_pr(
        number=42,
        url="pr-url",
        branch="feature/proj-1",
        reviews=[PullRequestReview("APPROVED", "x")],
        ci=[CheckStatus("SUCCESS")],
    )
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}], prs_by_task={"PROJ-1": [pr]}
    )

    _fake_worktree(tmp_path, "repo", "proj-1")
    app.rebuild()

    row = app.sections[0].rows[0]
    assert row.worktree is True
    assert row.marks == ("ok", "ok")
    assert row.title == "Task"
    assert s.task_pr_url("PROJ-1") == "pr-url"


# -- Row properties ----------------------------------------------------------


def test_row_properties(tmp_path):
    # Long identifiers are truncated, worktree keys are lowercased, missing titles get fallback
    _, _, app = _loaded_state(
        tmp_path,
        tasks=[
            {"identifier": "LONGPROJ-123", "title": "Long task", "url": "u1"},
        ],
    )

    row = app.sections[0].rows[0]
    assert row.key == "LONGPROJ-"
    assert row.wt_key == "longproj-123"
    assert row.title == "Long task"


# -- Section help ------------------------------------------------------------


def _row_help(s, row):
    return "  ".join(a.label for a in row.actions if a.enabled(s, row))


def test_task_row_actions(tmp_path):
    # Task row shows available actions — no session/PR so kill and PR are hidden
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    row = app.sections[0].rows[0]
    help_text = _row_help(s, row)
    for label in ["open", "fix", "linear", "PR"]:
        assert label in help_text
    assert "kill" not in help_text


def test_task_row_actions_with_session(tmp_path):
    # Task with active session shows kill
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    s.open_task("proj-1", "myrepo")

    row = app.sections[0].rows[0]
    assert "kill" in _row_help(s, row)


def test_task_row_actions_with_pr(tmp_path):
    # Task with a PR shows PR action
    pr = _make_pr(number=10, url="url1", branch="feature/proj-1")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}], prs_by_task={"PROJ-1": [pr]}
    )

    row = app.sections[0].rows[0]
    assert "PR" in _row_help(s, row)


def test_review_row_actions(tmp_path):
    # Review row shows delete instead of fix/linear
    review_pr = _make_pr(number=99, title="[PROJ-1] change")
    _fake_worktree(tmp_path, "repo", "review-99")
    s, _, app = _loaded_state(tmp_path, review_prs=[review_pr])
    app.next_tab()

    row = app.sections[0].rows[0]
    help_text = _row_help(s, row)
    for label in ["open", "delete", "PR"]:
        assert label in help_text
    assert "fix" not in help_text
    assert "linear" not in help_text
    assert "kill" not in help_text


# -- open_review() -----------------------------------------------------------


def test_open_review_creates_session_for_existing_worktree(tmp_path):
    # User selects a review PR that already has a checked-out worktree — session starts
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(number=99, title="[PROJ-1] fix", branch="proj-1-fix")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}], review_prs=[pr])

    s.open_review(pr.number, pr.repo_slug, pr.head_ref)

    assert s.has_session("review-99")


def test_open_review_reuses_session(tmp_path):
    # User opens the same review PR twice — session is reused, not duplicated
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(number=99, title="[PROJ-1] fix", branch="proj-1-fix")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}], review_prs=[pr])

    s.open_review(pr.number, pr.repo_slug, pr.head_ref)
    s.open_review(pr.number, pr.repo_slug, pr.head_ref)

    assert s.has_session("review-99")


def test_open_review_invalid_repo(tmp_path):
    # Review PR references a repo that isn't registered
    pr = _make_pr(number=99, title="[PROJ-1] fix", repo_slug="org/unknown")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    with pytest.raises(ValueError, match="not registered"):
        s.open_review(pr.number, pr.repo_slug, pr.head_ref)


# -- open_task() -------------------------------------------------------------


def test_open_task_creates_worktree_and_session(tmp_path):
    # User selects a task for the first time — worktree is created and tmux session starts
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")
    assert app.sections[0].rows[0].worktree is True
    assert app.sections[0].rows[0].session is True


def test_open_task_reuses_existing_worktree(tmp_path):
    # User reopens a task after killing the session — same worktree is reused
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

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
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.open_task("proj-1", "myrepo")

    assert s.has_session("proj-1")


def test_open_task_invalid_repo(tmp_path):
    # User tries to open a task with a repo that isn't registered
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    with pytest.raises(ValueError, match="not registered"):
        s.open_task("proj-1", "nonexistent")


# -- select() ---------------------------------------------------------------


def test_select_attaches_existing_session(tmp_path):
    # User presses enter on a task with a running session — attaches directly
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    s.open_task("proj-1", "myrepo")
    row = _task_row(app)

    dispatch("enter", row, s)

    # Session still exists — attach didn't kill it
    assert s.has_session("proj-1")


def test_select_task_picks_repo_and_opens(tmp_path):
    # User selects a task with no worktree — picks repo, then worktree + session are created
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    row = _task_row(app)

    with patch("jora.app.pick", return_value=0):
        dispatch("enter", row, s)
        _wait_loading(s)

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")


def test_select_task_cancelled_repo_pick(tmp_path):
    # User selects a task but cancels the repo picker — nothing happens
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    row = _task_row(app)

    with patch("jora.app.pick", return_value=None):
        dispatch("enter", row, s)

    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")


def test_select_task_with_worktree_skips_picker(tmp_path):
    # User selects a task that already has a worktree but no session — no repo picker shown
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")
    row = _task_row(app)

    with patch("jora.app.pick") as mock_pick:
        dispatch("enter", row, s)
        _wait_loading(s)

    mock_pick.assert_not_called()
    assert s.has_session("proj-1")


def test_select_no_repos_alerts(tmp_path):
    # User selects a task but has no repos registered — sees an alert
    s, alerts, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    row = _task_row(app)

    dispatch("enter", row, s)

    assert "No repos" in " ".join(alerts)


# -- open_task_pr() ----------------------------------------------------------


def test_open_pr_task_with_pr(tmp_path):
    # User presses 'p' on a task with a PR — URL is emitted
    opened = []
    pr = _make_pr(number=10, url="https://github.com/org/repo/pull/10", branch="proj-1")
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        prs_by_task={"PROJ-1": [pr]},
        on_open_url=lambda url: opened.append(url),
    )

    s.open_task_pr("PROJ-1")

    assert opened == ["https://github.com/org/repo/pull/10"]


def test_open_pr_task_without_pr(tmp_path):
    # User presses 'p' on a task with no PR — sees alert
    opened = []
    s, alerts, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        on_open_url=lambda url: opened.append(url),
    )

    s.open_task_pr("PROJ-1")

    assert opened == []
    assert "No PR" in " ".join(alerts)


def test_open_pr_review(tmp_path):
    # User presses 'p' on a review row — URL is emitted via on_open_url
    opened = []
    review_pr = _make_pr(number=99, title="fix", url="https://github.com/org/repo/pull/99")
    s, _, _ = _loaded_state(tmp_path, review_prs=[review_pr], on_open_url=lambda url: opened.append(url))

    s.on_open_url(review_pr.url)

    assert opened == ["https://github.com/org/repo/pull/99"]


# -- open_task_linear() ------------------------------------------------------


def test_open_task_linear(tmp_path):
    # User presses 'l' on a task — URL is emitted
    opened = []
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "https://linear.app/proj/PROJ-1"}],
        on_open_url=lambda url: opened.append(url),
    )

    s.open_task_linear("PROJ-1")

    assert opened == ["https://linear.app/proj/PROJ-1"]


# -- fix() -------------------------------------------------------------------


def test_fix_creates_worktree_and_session(tmp_path):
    # User presses 'f' to launch AI agent on a fresh task
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.fix("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")


def test_fix_blocks_when_session_running(tmp_path):
    # User presses 'f' but a session is already open — told to attach instead
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.fix("proj-1", "myrepo")

    assert "already running" in " ".join(alerts)


def test_fix_blocks_when_worktree_dirty(tmp_path):
    # User presses 'f' but the worktree has uncommitted changes — told to attach instead
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    wt = s.worktree_path("proj-1")
    (wt / "dirty.txt").write_text("dirty")

    s.fix("proj-1")

    assert "has changes" in " ".join(alerts)


def test_fix_action_picks_repo(tmp_path):
    # Fix action picks repo when no worktree exists, then creates worktree + session
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    row = _task_row(app)

    with patch("jora.app.pick", return_value=0):
        dispatch("fix", row, s)
        _wait_loading(s)

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")


def test_fix_action_existing_worktree_no_picker(tmp_path):
    # Fix action skips picker when worktree exists
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")
    row = _task_row(app)

    with patch("jora.app.pick") as mock_pick:
        dispatch("fix", row, s)

    mock_pick.assert_not_called()
    assert s.has_session("proj-1")


def test_fix_action_cancelled_repo_pick(tmp_path):
    # Fix action cancelled at repo picker — nothing happens
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])
    row = _task_row(app)

    with patch("jora.app.pick", return_value=None):
        dispatch("fix", row, s)

    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")


# -- kill_session() ----------------------------------------------------------


def test_kill_session_kills_running(tmp_path):
    # User presses 'x' to kill a running session
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    assert s.has_session("proj-1")

    s.kill_session("proj-1")
    assert not s.has_session("proj-1")
    assert "Killed" in " ".join(alerts)


def test_kill_session_no_session(tmp_path):
    # User presses 'x' but there's no session to kill
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.kill_session("proj-1")
    assert "No session" in " ".join(alerts)


# -- delete_worktree() -------------------------------------------------------


def test_delete_worktree_removes_worktree_and_session(tmp_path):
    # User presses 'd' on a review PR — worktree and session are both removed
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")

    s.delete_worktree("proj-1")
    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")
    assert "Removed" in " ".join(alerts)


def test_delete_worktree_without_session(tmp_path):
    # User deletes a worktree that has no running session — worktree removed, no session error
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")
    assert s.has_worktree("proj-1")
    assert not s.has_session("proj-1")

    s.delete_worktree("proj-1")
    assert not s.has_worktree("proj-1")
    assert "Removed" in " ".join(alerts)


def test_delete_worktree_no_worktree(tmp_path):
    # User presses 'd' but there's no worktree to delete
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.delete_worktree("proj-1")
    assert "No worktree" in " ".join(alerts)


# -- clean() -----------------------------------------------------------------


def test_clean_removes_stale_worktrees(tmp_path):
    # User presses 'c' — worktrees with no unique commits are cleaned up
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    s.clean()
    assert not s.has_worktree("proj-1")
    assert "Removed" in " ".join(alerts)


def test_clean_removes_merged_pr_worktree(tmp_path):
    # User presses 'c' — worktree whose PR was merged is cleaned even with unique commits
    _init_repo(tmp_path, "myrepo")

    class MergedGitHub(FakeGitHub):
        def is_branch_merged(self, slug, branch):
            return branch == "feature/proj-1"

    s, alerts, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        github=MergedGitHub(),
    )

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    # Add a unique commit so is_worktree_clean would return False
    wt = s.worktree_path("proj-1")
    (wt / "change.txt").write_text("x")
    _run(["git", "add", "."], cwd=str(wt))
    _run(["git", "commit", "-m", "local work"], cwd=str(wt))

    s.clean()
    assert not s.has_worktree("proj-1")
    assert "Removed" in " ".join(alerts)


def test_clean_keeps_dirty_unmerged_worktree(tmp_path):
    # User presses 'c' — worktree with unique commits and no merged PR is kept
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    s.open_task("proj-1", "myrepo")
    s.kill_session("proj-1")

    wt = s.worktree_path("proj-1")
    (wt / "change.txt").write_text("x")
    _run(["git", "add", "."], cwd=str(wt))
    _run(["git", "commit", "-m", "local work"], cwd=str(wt))

    s.clean()
    assert s.has_worktree("proj-1")
    assert "Nothing to clean" in " ".join(alerts)


def test_clean_nothing_to_clean(tmp_path):
    # User presses 'c' but there are no stale worktrees
    s, alerts, _ = _loaded_state(tmp_path)

    s.clean()
    assert "Nothing to clean" in " ".join(alerts)


# -- Queries -----------------------------------------------------------------


def test_queries(tmp_path):
    # User checks repo registration, worktree and session status throughout a task lifecycle
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}])

    assert s.repos() == ["myrepo"]
    assert not s.has_worktree("proj-1")
    assert not s.has_session("proj-1")

    s.open_task("proj-1", "myrepo")

    assert s.has_worktree("proj-1")
    assert s.has_session("proj-1")


def test_repos_sorted_by_usage(tmp_path):
    # Repos with more worktrees appear first in the picker
    _init_repo(tmp_path, "alpha")
    _init_repo(tmp_path, "beta")
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[
            {"identifier": "PROJ-1", "title": "Task 1", "url": "u1"},
            {"identifier": "PROJ-2", "title": "Task 2", "url": "u2"},
        ],
    )

    # no worktrees — alphabetical
    assert s.repos() == ["alpha", "beta"]

    # create worktrees in beta — beta should sort first
    s.open_task("proj-1", "beta")
    s.open_task("proj-2", "beta")
    s.kill_session("proj-1")
    s.kill_session("proj-2")

    assert s.repos()[0] == "beta"
