"""Interactive task picker UI."""

import argparse
import sys

from jora.config import Config
from jora.git import Git
from jora.tmux import Tmux
from jora import keychain
from jora.linear import LinearClient
from jora.github import GitHubClient
from jora.term import Menu
from jora.state import State

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
    parser = argparse.ArgumentParser(prog="jora", description="Linear task switcher with git worktrees")
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
        existing = keychain.get("linear")
        if existing and not args.reset:
            try:
                name = LinearClient(existing).whoami()
                print(f"Linear: authenticated as {name}")
            except Exception:
                print("Stored key is invalid — run: jora auth --reset")
        else:
            key = input("Linear API key (https://linear.app/settings/api): ").strip()
            if not key:
                print("No API key provided")
                sys.exit(1)
            try:
                name = LinearClient(key).whoami()
                keychain.store("linear", key)
                print(f"Linear: authenticated as {name}")
            except Exception as e:
                print(f"Invalid key: {e}", file=sys.stderr)
                sys.exit(1)
        try:
            print(f"GitHub: authenticated as {GitHubClient().whoami()}")
        except Exception:
            print("GitHub: not authenticated — run: gh auth login")
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

    api_key = keychain.get("linear")
    if not api_key:
        print("No API key — run: jora auth")
        sys.exit(1)
    linear = LinearClient(api_key)
    github = GitHubClient()

    with Menu(loading=True) as menu:
        s = State(git=git, tmux=tmux, linear=linear, github=github, menu=menu)
        s.load()

        while True:
            menu.loading = not s.done

            try:
                key, sec, row = menu.tick()
            except KeyboardInterrupt:
                break

            if key is None:
                continue
            if not sec or not row:
                continue
            for action in sec.actions:
                if action.matches(key):
                    if action.run(s, row) == "exit":
                        return
                    break
