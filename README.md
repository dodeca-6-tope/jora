# JORA (Jira Task Manager)

Interactive JIRA task manager with Git/GitHub integration.

## Setup

1. **Install:**

```bash
git clone <repository-url> jira-task-manager
cd jira-task-manager
./setup.sh
```

2. **Add to PATH:**

```bash
export PATH="$HOME/.local/bin:$PATH"  # Add to ~/.bashrc or ~/.zshrc
```

3. **Configure:** Go to your project and run `jira` to create `.env`, then edit it:

```bash
cd /your/project/directory
jira  # Creates .env file
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

Run `jira` in any project directory. Controls:

- ↑↓ Navigate • Enter: Action menu • q: Quit • r: Refresh • n: New task

**PR Status:** ✅ Approved • ❌ Changes requested • ⏳ Pending • 🚀 Ready • 📝 No PR

## Multiple Projects

Each project gets its own `.env` file:

```bash
cd ~/project-a && jira  # Uses project-a/.env
cd ~/project-b && jira  # Uses project-b/.env
```

## Important

- Add `.env` to `.gitignore`: `echo ".env" >> .gitignore`
- For GitHub PR status, install CLI: `brew install gh && gh auth login`
