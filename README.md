# JORA (Linear Task Manager)

**TL;DR**: Manage Linear tasks from terminal. Think in tasks, not branches.

> ⚠️ **Disclaimer**: This entire project was vibe-coded.

## Quick Start

```bash
# Install
git clone <repo> jora && cd jora && ./setup.sh

# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc

# Setup (creates .env file in repository root)
cd your-git-repository && jora
```

**Edit `.env`:**

```bash
LINEAR_API_KEY=lin_api_your_api_key_here
LINEAR_TEAM_KEY=YOUR_TEAM_KEY
LINEAR_WORKSPACE=your-workspace-name
```

[Get API key here](https://linear.app/settings/api)

**Finish setup:**

```bash
# Don't commit secrets (add to repository root .gitignore)
echo ".env" >> .gitignore
echo ".cache" >> .gitignore

# For PR features (optional)
brew install gh && gh auth login
```

## Commands

| Command   | What it does                                          |
| --------- | ----------------------------------------------------- |
| `jora` or `jora -i` | Interactive task browser - select and switch to tasks |
| `jora -c` | Commit staged changes with Linear task title          |
| `jora -p` | Create PR with task details                           |
| `jora -t` | Show current task key and title                       |

**Works with any branch**: `feature/PROJ-123` → auto-detects `PROJ-123`
