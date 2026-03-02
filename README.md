# Jora

Linear task manager for the terminal. Think in tasks, not branches.

Each task gets its own git worktree — switch between tasks without stashing or committing.

## Install

```bash
git clone <repo> jora && cd jora
uv tool install . --editable
```

Requires [uv](https://docs.astral.sh/uv/) and [gh](https://cli.github.com/) (`brew install uv gh && gh auth login`).

## Setup

Add a `.env` to any git repo where you want to use jora:

```bash
LINEAR_API_KEY=lin_api_...
LINEAR_TEAM_KEY=YOUR_TEAM_KEY
LINEAR_WORKSPACE=your-workspace-name
```

[Get API key here](https://linear.app/settings/api)

## Usage

```
jora
```

That's it. Shows your tasks, PR status, and CI status.

| Key     | Action                        |
| ------- | ----------------------------- |
| ↑/↓     | Navigate                      |
| enter   | Switch to task (worktree)     |
| o       | Open task in Linear           |
| p       | Open PR in browser            |
| r       | Refresh                       |
| q / esc | Quit                          |

Worktrees are created at `.worktrees/<task-key>/` inside your repo.
