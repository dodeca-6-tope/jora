import pytest

from jora.config import Config
from jora.git import Git
from jora.tmux import Tmux

TEST_TMUX_PREFIX = "test_jora_"


# -- tmux.session_name -------------------------------------------------------


def test_session_name():
    tmux = Tmux(prefix=TEST_TMUX_PREFIX)
    assert tmux.session_name("myrepo", "ltxd-123") == "test_jora_myrepo·ltxd-123"


def test_session_name_lowercases():
    tmux = Tmux(prefix=TEST_TMUX_PREFIX)
    assert tmux.session_name("MyRepo", "LTXD-123") == "test_jora_myrepo·ltxd-123"


def test_session_name_replaces_colons():
    tmux = Tmux(prefix=TEST_TMUX_PREFIX)
    assert tmux.session_name("repo", "a:b") == "test_jora_repo·a_b"


# -- jora peek ---------------------------------------------------------------


def test_peek_no_session(tmp_path):
    cfg = Config(jora_dir=tmp_path, tmux_prefix=TEST_TMUX_PREFIX)
    git = Git(cfg)
    tmux = Tmux(cfg.tmux_prefix)
    wt_dir = tmp_path / "worktrees" / "repo" / "test-1"
    wt_dir.mkdir(parents=True)
    (wt_dir / ".git").touch()
    wt = git.find_worktree_by_key("test-1")
    assert wt is not None
    name = tmux.session_name(wt.repo, wt.key)
    assert not tmux.has_session(name)


def test_peek_captures_session(tmp_path):
    import time

    cfg = Config(jora_dir=tmp_path, tmux_prefix=TEST_TMUX_PREFIX)
    git = Git(cfg)
    tmux = Tmux(cfg.tmux_prefix)
    wt_dir = tmp_path / "worktrees" / "repo" / "test-1"
    wt_dir.mkdir(parents=True)
    (wt_dir / ".git").touch()
    wt = git.find_worktree_by_key("test-1")
    name = tmux.session_name(wt.repo, wt.key)
    tmux.create_session(name, str(tmp_path))
    tmux.send_keys(name, "echo hello-from-peek")
    time.sleep(0.2)
    output = tmux.capture_pane(name)
    assert "hello-from-peek" in output
