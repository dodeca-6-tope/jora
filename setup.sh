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

echo -e "${BLUE}🚀 Setting up Jora...${NC}"
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
if ! pip install --upgrade pip; then
    echo -e "${RED}❌ Failed to upgrade pip${NC}"
    exit 1
fi

# Install dependencies
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    echo -e "${RED}❌ requirements.txt not found at $INSTALL_DIR/requirements.txt${NC}"
    exit 1
fi

echo -e "${YELLOW}📦 Installing Python dependencies...${NC}"
if ! pip install -r "$INSTALL_DIR/requirements.txt"; then
    echo -e "${RED}❌ Failed to install dependencies${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create global bin directory if it doesn't exist
if [ ! -d "$GLOBAL_BIN_DIR" ]; then
    echo -e "${YELLOW}📂 Creating global bin directory...${NC}"
    mkdir -p "$GLOBAL_BIN_DIR"
fi

# Create the global executable script
EXECUTABLE_SCRIPT="$GLOBAL_BIN_DIR/jora"
echo -e "${YELLOW}📝 Creating executable script...${NC}"

cat > "$EXECUTABLE_SCRIPT" << EOF
#!/bin/bash
# Jora - Global installation, project-specific configuration

# Installation directory (where the tool is installed)
INSTALL_DIR="$INSTALL_DIR"
VENV_DIR="\$INSTALL_DIR/.venv"

# Current working directory (for execution context)
WORKING_DIR="\$(pwd)"

# Get git repository root directory (where project config should be)
PROJECT_ROOT="\$(git rev-parse --show-toplevel 2>/dev/null || echo "\$WORKING_DIR")"

# Check if virtual environment exists
if [ ! -d "\$VENV_DIR" ]; then
    echo "❌ Virtual environment not found. Please run setup first:"
    echo "   cd $INSTALL_DIR && ./setup.sh"
    exit 1
fi

# Check if .env file exists in project root directory
if [ ! -f "\$PROJECT_ROOT/.env" ]; then
    echo "❌ No .env file found in project root directory: \$PROJECT_ROOT"
    echo "📝 Creating template .env file..."
    cat > "\$PROJECT_ROOT/.env" << 'ENVEOF'
# JIRA Configuration
# Get your API key from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=your.email@company.com
JIRA_API_KEY=your_jira_api_key_here
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
ENVEOF
    echo "✅ Created .env template at \$PROJECT_ROOT/.env"
    echo "⚠️  Please edit this file and add your JIRA credentials before running again"
    exit 1
fi

# Activate virtual environment and run the script
source "\$VENV_DIR/bin/activate"
cd "\$WORKING_DIR"
python3 "\$INSTALL_DIR/jora.py" "\$@"
EOF

# Make the executable script executable
chmod +x "$EXECUTABLE_SCRIPT"
echo -e "${GREEN}✅ Executable script created at $EXECUTABLE_SCRIPT${NC}"

echo
echo -e "${GREEN}🎉 Global setup complete!${NC}"
echo
echo -e "${BLUE}The tool is now installed globally and can be used from any directory.${NC}"
echo

# Check if the global bin directory is in PATH and offer to add it
if [[ ":$PATH:" != *":$GLOBAL_BIN_DIR:"* ]]; then
    echo -e "${YELLOW}⚠️  $GLOBAL_BIN_DIR is not in your PATH${NC}"
    echo
    
    # Detect shell and config file
    SHELL_NAME=$(basename "$SHELL")
    case "$SHELL_NAME" in
        "bash")
            SHELL_CONFIG="$HOME/.bashrc"
            if [[ ! -f "$SHELL_CONFIG" && -f "$HOME/.bash_profile" ]]; then
                SHELL_CONFIG="$HOME/.bash_profile"
            fi
            ;;
        "zsh")
            SHELL_CONFIG="$HOME/.zshrc"
            ;;
        "fish")
            SHELL_CONFIG="$HOME/.config/fish/config.fish"
            ;;
        *)
            SHELL_CONFIG="$HOME/.profile"
            ;;
    esac
    
    echo -e "${BLUE}Would you like me to automatically add $GLOBAL_BIN_DIR to your PATH?${NC}"
    echo -e "This will modify: ${YELLOW}$SHELL_CONFIG${NC}"
    echo
    read -p "Add to PATH automatically? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Create shell config if it doesn't exist
        if [[ ! -f "$SHELL_CONFIG" ]]; then
            touch "$SHELL_CONFIG"
            echo -e "${YELLOW}📝 Created $SHELL_CONFIG${NC}"
        fi
        
        # Check if PATH line already exists to prevent duplicates
        if grep -q "export PATH.*\.local/bin" "$SHELL_CONFIG"; then
            echo -e "${YELLOW}⚠️  PATH entry already exists in $SHELL_CONFIG${NC}"
        else
            # Add PATH export to shell config
            echo "" >> "$SHELL_CONFIG"
            echo "# Added by Jora setup" >> "$SHELL_CONFIG"
            echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$SHELL_CONFIG"
            echo -e "${GREEN}✅ Added $GLOBAL_BIN_DIR to PATH in $SHELL_CONFIG${NC}"
        fi
        
        # Ask if they want to source the file
        echo
        echo -e "${BLUE}Would you like me to reload your shell configuration now?${NC}"
        read -p "Source $SHELL_CONFIG? (y/n): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            source "$SHELL_CONFIG"
            echo -e "${GREEN}✅ Shell configuration reloaded${NC}"
            echo -e "${GREEN}✅ You can now use 'jora' from anywhere!${NC}"
        else
            echo -e "${YELLOW}⚠️  Please reload your shell or run: ${BLUE}source $SHELL_CONFIG${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Please manually add the following to your $SHELL_CONFIG:${NC}"
        echo -e "   ${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        echo -e "${YELLOW}   Then reload your shell or run: ${BLUE}source $SHELL_CONFIG${NC}"
    fi
else
    echo -e "${GREEN}✅ $GLOBAL_BIN_DIR is already in your PATH${NC}"
fi

echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Navigate to any git repository where you want to use Jora"
echo -e "2. Run ${YELLOW}jora${NC} - it will create a .env template file in the repository root"
echo -e "3. Edit the .env file with your JIRA credentials"
echo -e "4. Run ${YELLOW}jora${NC} again to start using the tool"
echo
echo -e "${BLUE}Usage examples (from anywhere within a git repository):${NC}"
echo -e "  ${YELLOW}jora${NC}                    - Start interactive task manager"
echo
echo -e "${BLUE}Each git repository will have its own .env file in the repository root with project-specific settings.${NC}"