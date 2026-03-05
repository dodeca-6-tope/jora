# Jora

Task switcher for Linear. Worktrees + tmux sessions per task, PR/CI status at a glance.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dodeca-6-tope/jora/main/setup.sh | bash
```

Installs jora, sets up shell integration (completions + cd wrapper), and prompts for your [Linear API key](https://linear.app/settings/api).

Requires [uv](https://docs.astral.sh/uv/) and [gh](https://cli.github.com/).

## Usage

```
jora
```

Pick a task, get a worktree and a tmux session. See PR reviews, CI status, and pending code reviews — all in one screen.

| Key     | Action                        |
| ------- | ----------------------------- |
| ↑/↓     | Navigate                      |
| enter   | Open task/review (worktree)   |
| f       | Launch AI fix agent           |
| x       | Kill tmux session             |
| d       | Delete worktree               |
| c       | Clean stale worktrees         |
| o       | Open task in Linear           |
| p       | Open PR in browser            |
| r       | Refresh                       |
| q / esc | Quit                          |

```
jora add <path-or-url>   # register a repo
jora remove <name>       # unregister a repo
jora auth                # set Linear API key + check GitHub auth
```

Worktrees are created at `~/.jora/worktrees/<repo>/<task-key>/`.

## Dev

```bash
uv run pytest
```
