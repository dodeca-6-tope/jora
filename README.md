# Jora

Task switcher for Linear. Worktrees + tmux sessions per task, PR/CI status at a glance.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dodeca-6-tope/jora/main/setup.sh | bash
```

Installs jora and sets up shell completions.

Requires [uv](https://docs.astral.sh/uv/) and [tmux](https://github.com/tmux/tmux).

## Usage

```
jora
```

Pick a task, get a worktree and a tmux session. See PR reviews, CI status, and pending code reviews — all in one screen.

| Key     | Action                        |
| ------- | ----------------------------- |
| ↑/↓     | Navigate                      |
| enter   | Open task/review (worktree)   |
| k       | Kill tmux session             |
| d       | Delete worktree               |
| c       | Clean stale worktrees         |
| l       | Open task in Linear           |
| p       | Open PR in browser            |
| r       | Refresh                       |
| tab     | Switch tab                    |
| q / esc | Quit                          |

```
jora add <path-or-url>   # register a repo
jora remove <name>       # unregister a repo
jora auth                # set Linear API key + GitHub token
```

Worktrees are created at `~/.jora/worktrees/<repo>/<task-key>/`.

## Dev

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format .   # format
```
