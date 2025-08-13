#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the absolute path to the project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="$PROJECT_ROOT/scripts/jira-task-manager"

echo -e "${BLUE}🚀 Setting up Jira Task Manager...${NC}"
echo

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed. Please install Python 3 and try again.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python 3 found${NC}"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 is not installed. Please install pip3 and try again.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ pip3 found${NC}"

# Create virtual environment if it doesn't exist
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}📦 Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${GREEN}✅ Virtual environment already exists${NC}"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo -e "${YELLOW}📦 Upgrading pip...${NC}"
pip install --upgrade pip

# Install dependencies
echo -e "${YELLOW}📦 Installing Python dependencies...${NC}"
pip install -r "$SCRIPT_DIR/requirements.txt"
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create .env file if it doesn't exist
ENV_FILE="$SCRIPT_DIR/.env"
ENV_TEMPLATE="$SCRIPT_DIR/env.template"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_TEMPLATE" ]; then
        cp "$ENV_TEMPLATE" "$ENV_FILE"
        echo -e "${YELLOW}📝 Created .env file from template${NC}"
        echo -e "${YELLOW}⚠️  Please edit $ENV_FILE and add your JIRA credentials${NC}"
    else
        echo -e "${YELLOW}📝 Creating .env file...${NC}"
        cat > "$ENV_FILE" << 'EOF'
# JIRA Configuration
# Get your API key from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_EMAIL=your.email@lightricks.com
JIRA_API_KEY=your_jira_api_key_here
JIRA_PROJECT_KEY=VL
EOF
        echo -e "${YELLOW}⚠️  Please edit $ENV_FILE and add your JIRA credentials${NC}"
    fi
else
    echo -e "${GREEN}✅ .env file already exists${NC}"
fi

# Create the executable script within the tool directory
EXECUTABLE_SCRIPT="$SCRIPT_DIR/jira"
echo -e "${YELLOW}📝 Creating executable script...${NC}"

cat > "$EXECUTABLE_SCRIPT" << EOF
#!/bin/bash
# Jira Task Manager - Run from within the tool directory

# Get the script directory (where this executable is located)
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="\$SCRIPT_DIR/.venv"

# Check if virtual environment exists
if [ ! -d "\$VENV_DIR" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   \$SCRIPT_DIR/setup.sh"
    exit 1
fi

# Activate virtual environment and run the script
source "\$VENV_DIR/bin/activate"
python3 "\$SCRIPT_DIR/jira_task_manager.py" "\$@"
EOF

# Make the executable script executable
chmod +x "$EXECUTABLE_SCRIPT"
echo -e "${GREEN}✅ Executable script created at $EXECUTABLE_SCRIPT${NC}"

echo
echo -e "${GREEN}🎉 Setup complete!${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Edit the configuration file: ${YELLOW}$ENV_FILE${NC}"
echo -e "2. Add your JIRA email and API key (get from: https://id.atlassian.com/manage-profile/security/api-tokens)"
echo -e "3. Run the tool: ${YELLOW}$EXECUTABLE_SCRIPT${NC}"
echo
echo -e "${BLUE}Usage examples:${NC}"
echo -e "  ${YELLOW}$EXECUTABLE_SCRIPT${NC}                    - List your incomplete tasks"
echo -e "  ${YELLOW}$EXECUTABLE_SCRIPT -i${NC}                 - Interactive mode with keyboard navigation"
echo -e "  ${YELLOW}$EXECUTABLE_SCRIPT -c${NC}                 - Create a new task"
echo -e "  ${YELLOW}$EXECUTABLE_SCRIPT 10${NC}                 - List up to 10 tasks"
echo -e "  ${YELLOW}$EXECUTABLE_SCRIPT -i 20${NC}              - Interactive mode with up to 20 tasks"