#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the installation directory (where this script is located)
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Global installation directory
GLOBAL_BIN_DIR="$HOME/.local/bin"

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
VENV_DIR="$INSTALL_DIR/.venv"
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
pip install -r "$INSTALL_DIR/requirements.txt"
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create global bin directory if it doesn't exist
if [ ! -d "$GLOBAL_BIN_DIR" ]; then
    echo -e "${YELLOW}📂 Creating global bin directory...${NC}"
    mkdir -p "$GLOBAL_BIN_DIR"
fi

# Create the global executable script
EXECUTABLE_SCRIPT="$GLOBAL_BIN_DIR/jira"
echo -e "${YELLOW}📝 Creating executable script...${NC}"

cat > "$EXECUTABLE_SCRIPT" << EOF
#!/bin/bash
# Jira Task Manager - Global installation, project-specific configuration

# Installation directory (where the tool is installed)
INSTALL_DIR="$INSTALL_DIR"
VENV_DIR="\$INSTALL_DIR/.venv"

# Current working directory (where project config should be)
WORKING_DIR="\$(pwd)"

# Check if virtual environment exists
if [ ! -d "\$VENV_DIR" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   cd $INSTALL_DIR && ./setup.sh"
    exit 1
fi

# Check if .env file exists in current directory
if [ ! -f "\$WORKING_DIR/.env" ]; then
    echo "❌ No .env file found in current directory: \$WORKING_DIR"
    echo "📝 Creating template .env file..."
    cat > "\$WORKING_DIR/.env" << 'ENVEOF'
# JIRA Configuration
# Get your API key from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_KEY=your_jira_api_key_here
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
ENVEOF
    echo "✅ Created .env template at \$WORKING_DIR/.env"
    echo "⚠️  Please edit this file and add your JIRA credentials before running again"
    exit 1
fi

# Activate virtual environment and run the script
source "\$VENV_DIR/bin/activate"
cd "\$WORKING_DIR"
python3 "\$INSTALL_DIR/jira_task_manager.py" "\$@"
EOF

# Make the executable script executable
chmod +x "$EXECUTABLE_SCRIPT"
echo -e "${GREEN}✅ Executable script created at $EXECUTABLE_SCRIPT${NC}"

echo
echo -e "${GREEN}🎉 Global setup complete!${NC}"
echo
echo -e "${BLUE}The tool is now installed globally and can be used from any directory.${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Add ${YELLOW}$GLOBAL_BIN_DIR${NC} to your PATH if it's not already there:"
echo -e "   ${YELLOW}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC} (add to your ~/.bashrc or ~/.zshrc)"
echo -e "2. Navigate to any project directory where you want to use JIRA"
echo -e "3. Run ${YELLOW}jira${NC} - it will create a .env template file"
echo -e "4. Edit the .env file with your JIRA credentials"
echo -e "5. Run ${YELLOW}jira${NC} again to start using the tool"
echo
echo -e "${BLUE}Usage examples (from any project directory):${NC}"
echo -e "  ${YELLOW}jira${NC}                    - List your incomplete tasks"
echo -e "  ${YELLOW}jira -i${NC}                 - Interactive mode with keyboard navigation"
echo -e "  ${YELLOW}jira -c${NC}                 - Create a new task"
echo -e "  ${YELLOW}jira 10${NC}                 - List up to 10 tasks"
echo -e "  ${YELLOW}jira -i 20${NC}              - Interactive mode with up to 20 tasks"
echo
echo -e "${BLUE}Each project directory will have its own .env file with project-specific settings.${NC}"