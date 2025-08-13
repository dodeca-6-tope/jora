# Jira Task Manager

Interactive JIRA task manager with Git/GitHub integration.

## Setup

```bash
./scripts/jira-task-manager/setup.sh
```

Configure credentials:

```bash
nano scripts/jira-task-manager/.env
```

Add:

```bash
JIRA_EMAIL=your.email@lightricks.com
JIRA_API_KEY=your_jira_api_key
JIRA_PROJECT_KEY=VL
```

Get API key: [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

## Usage

```bash
scripts/jira-task-manager/jira
```

**Controls:**

- ↑↓ Navigate tasks
- Enter: Action menu
- q: Quit
- r: Refresh
- n: New task

**PR Status:**

- ✅ Approved
- ❌ Changes requested
- ⏳ Pending review
- 🚀 Ready to launch
- 📝 No PR

## Troubleshooting

**Setup issues:**

```bash
./scripts/jira-task-manager/setup.sh
chmod +x scripts/jira-task-manager/jira
```

**Dependencies:**

```bash
cd scripts/jira-task-manager
source .venv/bin/activate
pip install -r requirements.txt
```

**Git/GitHub:**

- Install GitHub CLI: `brew install gh`
- Authenticate: `gh auth login`
