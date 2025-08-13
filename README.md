# Jira Task Manager

Interactive JIRA task manager with Git/GitHub integration.

## Features

- 📋 List and manage your JIRA tasks from the command line
- 🔍 Filter tasks by status and priority
- 🎯 Interactive keyboard navigation
- 📝 Create new tasks directly from terminal
- 🔗 Git/GitHub integration for PR status tracking
- 🌍 Global installation with per-project configuration
- 🔒 Secure credential management per project

## Quick Start

```bash
# 1. Install globally
git clone <repository-url> jira-task-manager
cd jira-task-manager
./setup.sh

# 2. Use in any project
cd /your/project/directory
jira  # Creates .env template, edit with your JIRA details
jira  # Start managing tasks!
```

## Global Installation

Install the tool once, use it from any project directory:

```bash
# Clone and install globally
git clone <repository-url> jira-task-manager
cd jira-task-manager
./setup.sh
```

Add to your PATH (if not already there):

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"
```

## Per-Project Usage

Navigate to any project directory and run:

```bash
cd /path/to/your/project
jira
```

On first run, it will create a `.env` template file. Edit it with your project-specific settings:

```bash
# Edit the generated .env file
nano .env
```

Configure with your JIRA details:

```bash
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_KEY=your_jira_api_key_here
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
```

Get API key: [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

## Usage

From any project directory (after configuring `.env`):

```bash
jira
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

**Command Options:**

- `jira` - List your incomplete tasks
- `jira -i` - Interactive mode with keyboard navigation  
- `jira -c` - Create a new task
- `jira 10` - List up to 10 tasks
- `jira -i 20` - Interactive mode with up to 20 tasks

## Project Structure

Each project directory will have its own `.env` file with project-specific JIRA settings. This allows you to:

- Work with different JIRA instances
- Use different project keys per repository  
- Keep credentials separate between projects

**Example workflow:**

```bash
# Install once
git clone <repo> jira-task-manager && cd jira-task-manager && ./setup.sh

# Use in project A
cd ~/projects/website
jira  # Creates .env, edit with website JIRA settings
jira -i  # Interactive mode for website tasks

# Use in project B  
cd ~/projects/mobile-app
jira  # Creates separate .env, edit with mobile JIRA settings
jira -c  # Create new task for mobile project
```

## Installation Details

The setup script will:

1. Create a Python virtual environment in the installation directory
2. Install required dependencies (`requests`, `python-dotenv`)
3. Create a global `jira` executable in `~/.local/bin/`
4. Configure the tool to look for `.env` files in your current working directory

## Security

⚠️ **Important**: Add `.env` to your project's `.gitignore` file to avoid committing API keys:

```bash
# Add to .gitignore
echo ".env" >> .gitignore
```

The `.env` file contains sensitive information (API keys) and should never be committed to version control.

## Troubleshooting

**Setup issues:**

```bash
# Re-run global installation
cd /path/to/jira-task-manager
./setup.sh

# Check if ~/.local/bin is in PATH
echo $PATH | grep ".local/bin"

# Add to PATH if missing
export PATH="$HOME/.local/bin:$PATH"
```

**Configuration issues:**

```bash
# Check if .env exists in current directory
ls -la .env

# Create .env template
jira  # Will create template if missing

# Validate configuration
cat .env
```

**Dependencies:**

```bash
# Check installation directory
ls -la ~/.local/bin/jira

# Check virtual environment
ls -la /path/to/jira-task-manager/.venv
```

**Git/GitHub:**

- Install GitHub CLI: `brew install gh`
- Authenticate: `gh auth login`
