# Jora

Linear task manager for the terminal. Think in tasks, not branches.

Each task gets its own git worktree — switch between tasks without stashing or committing.

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

Shows your tasks, PR status, and CI status. Pick a task to switch into its worktree.

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
