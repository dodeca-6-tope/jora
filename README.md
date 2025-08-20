# JORA (Jira Task Manager)

Interactive JIRA task manager with Git/GitHub integration.

## Setup

1. **Install:**

```bash
git clone <repository-url> jora
cd jora
./setup.sh
```

2. **Add to PATH:**

```bash
export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc
```

3. **Configure:** Go to your project and run `jora` to create `.env`, then edit it:

```bash
cd /your/project/directory
jora  # Creates .env file
```

Edit `.env` with your JIRA details:

```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_KEY=your_jira_api_key_here
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
```

Get API key: [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

## Usage

Jora supports two main modes:

### Interactive Mode

Run the interactive task manager to browse and manage JIRA tasks:

```bash
jora -i
# or
jora --interactive
```

**Controls:**

- ↑↓ Navigate • Enter: Action menu • q: Quit • r: Refresh • n: New task

**PR Status:** ✅ Approved • ❌ Changes requested • ⏳ Pending • 🚀 Ready • 📝 No PR

### Commit Mode

Stage all changes and commit with the JIRA task title from the current branch:

```bash
jora -c
# or
jora --commit-with-title
```

This command extracts the task key from your current branch (e.g., `feature/PROJ-123`) and uses the JIRA task title as the commit message.

### PR Mode

Create a pull request for the task associated with the current branch:

```bash
jora -p
# or
jora --create-pr
```

This command extracts the task key from your current branch (e.g., `feature/PROJ-123`), fetches the task details from JIRA, and creates a PR using the GitHub CLI with the task title and key.

### Help

View all available options:

```bash
jora
```

## Multiple Projects

Each project gets its own `.env` file:

```bash
cd ~/project-a && jora -i  # Uses project-a/.env
cd ~/project-b && jora -i  # Uses project-b/.env
```

## Important

- Add `.env` to `.gitignore`: `echo ".env" >> .gitignore`
- For GitHub PR status, install CLI: `brew install gh && gh auth login`
