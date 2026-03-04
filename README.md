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

| Key     | Action                    |
| ------- | ------------------------- |
| ↑/↓     | Navigate                  |
| enter   | Switch to task (worktree) |
| o       | Open task in Linear       |
| p       | Open PR in browser        |
| r       | Refresh                   |
| q / esc | Quit                      |

Worktrees are created at `~/.jora/worktrees/<repo>/<task-key>/`.
