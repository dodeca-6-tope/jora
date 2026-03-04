# Jora

Linear task manager for the terminal. Think in tasks, not branches.

Each task gets its own git worktree — switch between tasks without stashing or committing.

## Install

```bash
git clone <repo> jora && cd jora
uv tool install . --editable
eval "$(jora init zsh)"  # add to .zshrc (or: jora init zsh > ~/.oh-my-zsh/custom/jora.zsh)
```

Requires [uv](https://docs.astral.sh/uv/) and [gh](https://cli.github.com/) (`brew install uv gh && gh auth login`).

## Setup

Add a `.env` to any git repo where you want to use jora:

```bash
LINEAR_API_KEY=lin_api_...
```

[Get API key here](https://linear.app/settings/api)

## Usage

```
jora
```

Shows your tasks, PR status, and CI status. Pick a task to switch into its worktree.

| Key     | Action                    |
| ------- | ------------------------- |
| ↑/↓     | Navigate                  |
| enter   | Switch to task (worktree) |
| o       | Open task in Linear       |
| p       | Open PR in browser        |
| r       | Refresh                   |
| q / esc | Quit                      |

Worktrees are created at `~/.jora/worktrees/<repo>/<task-key>/`.
