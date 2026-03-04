#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/dodeca-6-tope/jora.git"
CUSTOM_DIR="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"

# -- Install uv if missing ----------------------------------------------------
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# -- Install jora --------------------------------------------------------------
echo "Installing jora..."
uv tool install --force "git+$REPO"

# -- Add shell wrapper ---------------------------------------------------------
WRAPPER="$CUSTOM_DIR/jora.zsh"
if [[ -f "$WRAPPER" ]]; then
  echo "Shell wrapper already exists at $WRAPPER"
else
  mkdir -p "$CUSTOM_DIR"
  cat > "$WRAPPER" << 'EOF'
jora() {
  command jora "$@"
  if [[ -f /tmp/jora_cd ]]; then
    local dir=$(cat /tmp/jora_cd)
    local cmd=$(cat /tmp/jora_cmd 2>/dev/null)
    rm -f /tmp/jora_cd /tmp/jora_cmd
    cd "$dir"
    [[ -n "$cmd" ]] && eval "$cmd"
  fi
}
EOF
  echo "Added shell wrapper to $WRAPPER"
fi

echo ""
echo "Done! Next steps:"
echo "  1. Restart your shell or run: source $WRAPPER"
echo "  2. Add a .env to your repo with: LINEAR_API_KEY=lin_api_..."
echo "     (Get one at https://linear.app/settings/api)"
echo "  3. Run: jora"
