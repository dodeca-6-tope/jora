# JORA (Jira Task Manager)

**TL;DR**: Manage JIRA tasks from terminal. Think in tasks, not branches.

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
JIRA_URL=https://company.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_KEY=get_from_atlassian
JIRA_PROJECT_KEY=PROJ
```

[Get API key here](https://id.atlassian.com/manage-profile/security/api-tokens)

**Finish setup:**

```bash
# Don't commit secrets (add to repository root .gitignore)
echo ".env" >> .gitignore

# For PR features (optional)
brew install gh && gh auth login
```

## Commands

| Command   | What it does                                                  |
| --------- | ------------------------------------------------------------- |
| `jora -i` | Interactive task browser - select and switch to tasks         |
| `jora -f` | Implement task using AI agent based on JIRA description       |
| `jora -r` | Review all work on branch using AI agent, fix issues if found |
| `jora -a` | Address unresolved PR comments using AI agent                 |
| `jora -c` | Commit staged changes with JIRA task title                    |
| `jora -p` | Create PR with task details                                   |
| `jora -t` | Show current task title                                       |
| `jora`    | Show help                                                     |

**Works with any branch**: `feature/PROJ-123` → auto-detects `PROJ-123`
