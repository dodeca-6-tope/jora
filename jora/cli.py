"""Interactive task picker UI."""

import argparse
import collections
import sys
import webbrowser

from jora import creds
from jora.app import App, dispatch, term
from jora.config import Config
from jora.git import Git
from jora.github import GitHubClient
from jora.linear import LinearClient
from jora.store import Store
from jora.tmux import Tmux

# -- Shell init (jora init <shell>) ------------------------------------------

_SHELL_INIT = """\
jora() {
  command jora "$@"
  if [[ -f ~/.jora/cd ]]; then
    cd "$(cat ~/.jora/cd)"
    rm -f ~/.jora/cd
  fi
}
_jora() {
  if (( CURRENT == 2 )); then
    compadd auth init add remove
  elif (( CURRENT == 3 )); then
    case $words[2] in
      remove) compadd $(ls ~/.jora/repos/ 2>/dev/null) ;;
      add) _directories ;;
      init) ;;
    esac
  fi
}
compdef _jora jora
"""


# -- Entry point --------------------------------------------------------------


def _parse_args():
    parser = argparse.ArgumentParser(
        prog="jora", description="Linear task switcher with git worktrees"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="print shell init script (zsh)")
    auth_p = sub.add_parser("auth", help="set Linear API key")
    auth_p.add_argument("--reset", action="store_true", help="replace existing key")

    add_p = sub.add_parser("add", help="register a repo")
    add_p.add_argument("target", help="local path (symlink) or git URL (clone)")

    rm_p = sub.add_parser("remove", help="unregister a repo")
    rm_p.add_argument("name", help="repo name from ~/.jora/repos/")

    return parser.parse_args()


def main():
    cfg = Config()
    git = Git(cfg)
    tmux = Tmux(cfg.tmux_prefix)
    args = _parse_args()

    if args.command == "init":
        print(_SHELL_INIT)
        return

    if args.command == "auth":
        creds.auth(
            "Linear",
            "linear",
            "https://linear.app/settings/api",
            lambda k: LinearClient(k).whoami(),
            args.reset,
        )
        creds.auth(
            "GitHub",
            "github",
            "https://github.com/settings/tokens",
            lambda k: GitHubClient(k).whoami(),
            args.reset,
        )
        return

    if args.command == "add":
        try:
            name = git.add_repo(args.target)
            print(f"Added {name}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.command == "remove":
        try:
            git.remove_repo(args.name)
            print(f"Removed {args.name}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    linear = LinearClient(creds.require("linear", "Linear"))
    github = GitHubClient(creds.require("github", "GitHub"))

    pending = collections.deque()
    app = None
    s = Store(
        git=git,
        tmux=tmux,
        linear=linear,
        github=github,
        on_alert=lambda text: app.alert(text),
        on_attach=lambda name: (
            term.suspend(),
            tmux.attach_session(name),
            term.resume(),
        ),
        on_open_url=webbrowser.open,
        on_defer=pending.append,
        on_change=lambda: app.rebuild(),
    )
    app = App(store=s)

    with app:
        s.load()

        while True:
            try:
                while pending:
                    pending.popleft()()
                key, row = app.tick()
            except KeyboardInterrupt:
                break

            if key == "focus":
                s.maybe_reload(force=True)
                continue
            if key == "tab":
                app.switch_tab(1, wrap=True)
                continue
            if key == "right":
                app.switch_tab(1)
                continue
            if key == "left":
                app.switch_tab(-1)
                continue
            if dispatch(key, row, s) == "exit":
                return
            if not key:
                s.maybe_reload()
