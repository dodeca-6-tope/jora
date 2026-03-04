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
mkdir -p "$HOME/.jora"
uv tool install --force "git+$REPO"

# -- Shell integration ---------------------------------------------------------
mkdir -p "$CUSTOM_DIR"
jora init > "$CUSTOM_DIR/jora.zsh"
echo "Shell integration → $CUSTOM_DIR/jora.zsh"

# -- Linear API key ------------------------------------------------------------
ENV_FILE="$HOME/.jora/.env"
if grep -q "LINEAR_API_KEY=" "$ENV_FILE" 2>/dev/null; then
  echo "Linear API key → already set"
else
  printf "Linear API key (get one at https://linear.app/settings/api): "
  read -r key
  if [[ -n "$key" ]]; then
    echo "LINEAR_API_KEY=$key" > "$ENV_FILE"
    echo "Linear API key → $ENV_FILE"
  else
    echo "Skipped — add LINEAR_API_KEY to ~/.jora/.env later"
  fi
fi

echo ""
echo "Done — restart your shell, then run: jora"
