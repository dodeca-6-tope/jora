import shutil
import subprocess
import time
from unittest.mock import patch

import pytest

from jora.app import App, dispatch
from jora.config import Config
from jora.git import Git, Worktree
from jora.github import CheckStatus, PullRequest, PullRequestReview
from jora.linear import Tracker
from jora.state import State, _noop
from jora.tmux import Tmux
from tests.mocks import FakeGitHub, FakeTracker

# -- Helpers -----------------------------------------------------------------

TEST_TMUX_PREFIX = "test_jora_"
WT = Worktree("myrepo", "proj-1")


def _wait_done(s, timeout=5):
    deadline = time.monotonic() + timeout
    while not s.done:
        if time.monotonic() > deadline:
            raise TimeoutError("load did not complete")
        time.sleep(0.01)


def _make_pr(
    number=1, title="", url="", branch="", reviews=None, ci=None, repo_slug="org/repo"
):
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


def _make_state(
    tmp_path,
    tasks=None,
    prs_by_task=None,
    review_prs=None,
    linear=None,
    github=None,
    on_open_url=_noop,
):
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
        "PROJ-4": [
            _make_pr(number=40, branch="feature/proj-4", ci=[CheckStatus("PENDING")])
        ],
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
    s, _, app = _loaded_state(tmp_path)

    assert s.done
    assert len(app.sections) == 1
    assert app.sections[0].rows == []


def test_load_error_sets_message(tmp_path):
    class FailingTracker(Tracker):
        def whoami(self):
            return ""

        def fetch_tasks(self):
            raise RuntimeError("API down")

    _, alerts, _ = _loaded_state(tmp_path, linear=FailingTracker())

    assert "API down" in " ".join(alerts)


def test_load_sets_done(tmp_path):
    s, _, _ = _make_state(tmp_path)
    assert not s.done
    s.load()
    _wait_done(s)
    assert s.done


def test_load_detects_existing_worktrees(tmp_path):
    _fake_worktree(tmp_path, "myrepo", "proj-1")
    _, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    assert app.sections[0].rows[0].worktree is True


# -- Reviews -----------------------------------------------------------------


def test_review_shown_with_worktree(tmp_path):
    review_pr = _make_pr(
        number=99, title="[PROJ-5] change", branch="proj-5-fix", repo_slug="org/repo"
    )
    _fake_worktree(tmp_path, "repo", "review-99")

    _, _, app = _loaded_state(tmp_path, review_prs=[review_pr])
    app.next_tab()

    assert len(app.sections) == 1
    row = app.sections[0].rows[0]
    assert row.key == "99"
    assert row.title == "[PROJ-5] change"
    assert row.worktree is True


def test_review_shows_pr_title(tmp_path):
    _, _, app = _loaded_state(
        tmp_path, review_prs=[_make_pr(number=77, title="fix typo", branch="random")]
    )
    app.next_tab()

    row = app.sections[0].rows[0]
    assert row.title == "fix typo"
    assert row.key == "77"


# -- rebuild ---------------------------------------------------------------


def test_rebuild_tracks_worktree_lifecycle(tmp_path):
    _, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    assert app.sections[0].rows[0].worktree is False

    wt = _fake_worktree(tmp_path, "repo", "proj-1")
    app.rebuild()
    assert app.sections[0].rows[0].worktree is True

    shutil.rmtree(wt)
    app.rebuild()
    assert app.sections[0].rows[0].worktree is False


def test_rebuild_preserves_data(tmp_path):
    pr = _make_pr(
        number=42,
        url="pr-url",
        branch="feature/proj-1",
        reviews=[PullRequestReview("APPROVED", "x")],
        ci=[CheckStatus("SUCCESS")],
    )
    s, _, app = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        prs_by_task={"PROJ-1": [pr]},
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
    _, _, app = _loaded_state(
        tmp_path,
        tasks=[
            {"identifier": "LONGPROJ-123", "title": "Long task", "url": "u1"},
        ],
    )

    row = app.sections[0].rows[0]
    assert row.key == "LONGPROJ-"
    assert row.title == "Long task"


# -- Section help ------------------------------------------------------------


def _row_help(s, row):
    return "  ".join(a.label for a in row.actions if a.enabled(s, row))


def test_task_row_actions(tmp_path):
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    row = app.sections[0].rows[0]
    help_text = _row_help(s, row)
    for label in ["open", "fix", "linear", "PR"]:
        assert label in help_text
    assert "kill" not in help_text


def test_task_row_actions_with_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)

    row = app.sections[0].rows[0]
    assert "kill" in _row_help(s, row)


def test_task_row_actions_with_pr(tmp_path):
    pr = _make_pr(number=10, url="url1", branch="feature/proj-1")
    s, _, app = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        prs_by_task={"PROJ-1": [pr]},
    )

    row = app.sections[0].rows[0]
    assert "PR" in _row_help(s, row)


def test_review_row_actions(tmp_path):
    review_pr = _make_pr(number=99, title="[PROJ-1] change", repo_slug="org/repo")
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
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(
        number=99, title="[PROJ-1] fix", branch="proj-1-fix", repo_slug="org/repo"
    )
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        review_prs=[pr],
    )

    wt = s.create_review_worktree(99, "org/repo", "proj-1-fix")
    s.create_session(wt)

    assert s.has_session(wt)


def test_open_review_reuses_session(tmp_path):
    _fake_worktree(tmp_path, "repo", "review-99")
    pr = _make_pr(
        number=99, title="[PROJ-1] fix", branch="proj-1-fix", repo_slug="org/repo"
    )
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        review_prs=[pr],
    )

    wt = s.create_review_worktree(99, "org/repo", "proj-1-fix")
    s.create_session(wt)
    s.create_session(wt)

    assert s.has_session(wt)


def test_open_review_invalid_repo(tmp_path):
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    with pytest.raises(ValueError, match="not registered"):
        s.create_review_worktree(99, "org/unknown", "proj-1-fix")


# -- open_task() -------------------------------------------------------------


def test_open_task_creates_worktree_and_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)

    assert s.git.find_worktree(wt)
    assert s.has_session(wt)
    assert app.sections[0].rows[0].worktree is True
    assert app.sections[0].rows[0].session is True


def test_open_task_reuses_existing_worktree(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt1 = s.create_task_worktree("proj-1", "myrepo")
    wt2 = s.create_task_worktree("proj-1", "myrepo")

    assert wt1 == wt2


def test_open_task_reuses_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.create_task_worktree("proj-1", "myrepo")

    assert s.has_session(wt)


def test_open_task_invalid_repo(tmp_path):
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    with pytest.raises(ValueError, match="not registered"):
        s.create_task_worktree("proj-1", "nonexistent")


# -- select() ---------------------------------------------------------------


def test_select_attaches_existing_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    row = _task_row(app)

    dispatch("enter", row, s)

    assert s.has_session(wt)


def test_select_task_picks_repo_and_opens(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    row = _task_row(app)

    with patch("jora.app.pick", return_value=0):
        dispatch("enter", row, s)
        _wait_loading(s)

    assert s.git.find_worktree(Worktree("myrepo", "proj-1"))
    assert s.has_session(Worktree("myrepo", "proj-1"))


def test_select_task_cancelled_repo_pick(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    row = _task_row(app)

    with patch("jora.app.pick", return_value=None):
        dispatch("enter", row, s)

    assert not s.git.find_worktree(Worktree("myrepo", "proj-1"))


def test_select_task_with_worktree_skips_picker(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)
    row = _task_row(app)

    with patch("jora.app.pick") as mock_pick:
        dispatch("enter", row, s)
        _wait_loading(s)

    mock_pick.assert_not_called()
    assert s.has_session(wt)


def test_select_no_repos_alerts(tmp_path):
    s, alerts, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    row = _task_row(app)

    dispatch("enter", row, s)

    assert "No repos" in " ".join(alerts)


# -- open_task_linear() ------------------------------------------------------


def test_open_task_linear(tmp_path):
    opened = []
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[
            {
                "identifier": "PROJ-1",
                "title": "Task",
                "url": "https://linear.app/proj/PROJ-1",
            }
        ],
        on_open_url=lambda url: opened.append(url),
    )

    s.open_task_linear("PROJ-1")

    assert opened == ["https://linear.app/proj/PROJ-1"]


# -- fix() -------------------------------------------------------------------


def test_fix_creates_worktree_and_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    s.fix("proj-1", "myrepo")

    wt = Worktree("myrepo", "proj-1")
    assert s.git.find_worktree(wt)
    assert s.has_session(wt)


def test_fix_blocks_when_session_running(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.fix("proj-1", "myrepo")

    assert "already running" in " ".join(alerts)


def test_fix_blocks_when_worktree_dirty(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)

    path = s.git.find_worktree(wt)
    (path / "dirty.txt").write_text("dirty")

    s.fix("proj-1")

    assert "has changes" in " ".join(alerts)


def test_fix_action_picks_repo(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    row = _task_row(app)

    with patch("jora.app.pick", return_value=0):
        dispatch("fix", row, s)
        _wait_loading(s)

    wt = Worktree("myrepo", "proj-1")
    assert s.git.find_worktree(wt)
    assert s.has_session(wt)


def test_fix_action_existing_worktree_no_picker(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)
    row = _task_row(app)

    with patch("jora.app.pick") as mock_pick:
        dispatch("fix", row, s)

    mock_pick.assert_not_called()
    assert s.has_session(wt)


def test_fix_action_cancelled_repo_pick(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, app = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )
    row = _task_row(app)

    with patch("jora.app.pick", return_value=None):
        dispatch("fix", row, s)

    assert not s.git.find_worktree(Worktree("myrepo", "proj-1"))


# -- kill_session() ----------------------------------------------------------


def test_kill_session_kills_running(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    assert s.has_session(wt)

    s.kill_session(wt)
    assert not s.has_session(wt)
    assert "Killed" in " ".join(alerts)


def test_kill_session_no_session(tmp_path):
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    s.kill_session(Worktree("myrepo", "proj-1"))
    assert "No session" in " ".join(alerts)


# -- delete_worktree() -------------------------------------------------------


def test_delete_worktree_removes_worktree_and_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    assert s.git.find_worktree(wt)
    assert s.has_session(wt)

    s.delete_worktree(wt)
    assert not s.git.find_worktree(wt)
    assert not s.has_session(wt)
    assert "Removed" in " ".join(alerts)


def test_delete_worktree_without_session(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)
    assert s.git.find_worktree(wt)
    assert not s.has_session(wt)

    s.delete_worktree(wt)
    assert not s.git.find_worktree(wt)
    assert "Removed" in " ".join(alerts)


def test_delete_worktree_no_worktree(tmp_path):
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    s.delete_worktree(Worktree("myrepo", "proj-1"))
    assert "No worktree" in " ".join(alerts)


# -- clean() -----------------------------------------------------------------


def test_clean_removes_stale_worktrees(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)

    s.clean()
    assert not s.git.find_worktree(wt)
    assert "Removed" in " ".join(alerts)


def test_clean_removes_merged_pr_worktree(tmp_path):
    _init_repo(tmp_path, "myrepo")

    class MergedGitHub(FakeGitHub):
        def is_branch_merged(self, slug, branch):
            return branch == "feature/proj-1"

    s, alerts, _ = _loaded_state(
        tmp_path,
        tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}],
        github=MergedGitHub(),
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)

    path = s.git.find_worktree(wt)
    (path / "change.txt").write_text("x")
    _run(["git", "add", "."], cwd=str(path))
    _run(["git", "commit", "-m", "local work"], cwd=str(path))

    s.clean()
    assert not s.git.find_worktree(wt)
    assert "Removed" in " ".join(alerts)


def test_clean_keeps_dirty_unmerged_worktree(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, alerts, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)
    s.kill_session(wt)

    path = s.git.find_worktree(wt)
    (path / "change.txt").write_text("x")
    _run(["git", "add", "."], cwd=str(path))
    _run(["git", "commit", "-m", "local work"], cwd=str(path))

    s.clean()
    assert s.git.find_worktree(wt)
    assert "Nothing to clean" in " ".join(alerts)


def test_clean_nothing_to_clean(tmp_path):
    s, alerts, _ = _loaded_state(tmp_path)

    s.clean()
    assert "Nothing to clean" in " ".join(alerts)


# -- Queries -----------------------------------------------------------------


def test_queries(tmp_path):
    _init_repo(tmp_path, "myrepo")
    s, _, _ = _loaded_state(
        tmp_path, tasks=[{"identifier": "PROJ-1", "title": "Task", "url": "u1"}]
    )

    assert s.repos() == ["myrepo"]

    wt = s.create_task_worktree("proj-1", "myrepo")
    s.create_session(wt)

    assert s.git.find_worktree(wt)
    assert s.has_session(wt)


def test_repos_sorted_by_usage(tmp_path):
    _init_repo(tmp_path, "alpha")
    _init_repo(tmp_path, "beta")
    s, _, _ = _loaded_state(
        tmp_path,
        tasks=[
            {"identifier": "PROJ-1", "title": "Task 1", "url": "u1"},
            {"identifier": "PROJ-2", "title": "Task 2", "url": "u2"},
        ],
    )

    assert s.repos() == ["alpha", "beta"]

    s.create_task_worktree("proj-1", "beta")
    s.create_task_worktree("proj-2", "beta")

    assert s.repos()[0] == "beta"
