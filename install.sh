#!/usr/bin/env bash
#
# install.sh — set up claudevm on this Mac.
#
# Safe to re-run: it overwrites the shared template/allowlist files but never
# touches your per-project instances under ~/.local/var/claudevm/instances/.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDEVM_HOME="${CLAUDEVM_HOME:-$HOME/.config/claudevm}"

echo "==> Checking dependencies"
if ! command -v limactl >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Lima not found. Installing via Homebrew..."
    brew install lima
  else
    echo "Lima not found and Homebrew isn't available." >&2
    echo "Install Homebrew first (https://brew.sh), then run: brew install lima" >&2
    exit 1
  fi
else
  echo "Found $(limactl --version)"
fi

if ! command -v code >/dev/null 2>&1; then
  echo "Note: the 'code' CLI isn't on your PATH yet."
  echo "  In VS Code: Cmd+Shift+P -> 'Shell Command: Install code command in PATH'"
  echo "  (Only needed for 'claudevm code'; everything else works without it.)"
fi

echo "==> Installing templates to $CLAUDEVM_HOME"
mkdir -p "$CLAUDEVM_HOME"
cp "$REPO_DIR/claude-sandbox.yaml" "$CLAUDEVM_HOME/"
cp "$REPO_DIR/default-allowlist.txt" "$CLAUDEVM_HOME/"

echo "==> Installing the claudevm command"
BIN_DIR=""
for candidate in "$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
  if [ -d "$candidate" ] && [ -w "$candidate" ]; then
    BIN_DIR="$candidate"
    break
  fi
done
if [ -z "$BIN_DIR" ]; then
  BIN_DIR="$HOME/.local/bin"
  mkdir -p "$BIN_DIR"
fi

cp "$REPO_DIR/claudevm" "$BIN_DIR/claudevm"
chmod +x "$BIN_DIR/claudevm"
echo "Installed to $BIN_DIR/claudevm"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo
    echo "NOTE: $BIN_DIR is not on your PATH. Add this to ~/.zshrc (or ~/.bash_profile):"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
    echo
    ;;
esac

echo "==> Configuring SSH for VS Code Remote-SSH into Lima VMs"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
SSH_CONFIG="$HOME/.ssh/config"
touch "$SSH_CONFIG"
if ! grep -qF 'Include ~/.lima/*/ssh.config' "$SSH_CONFIG"; then
  { echo 'Include ~/.lima/*/ssh.config'; echo; cat "$SSH_CONFIG"; } > "$SSH_CONFIG.tmp"
  cp -f "$SSH_CONFIG" "$SSH_CONFIG~"
  mv -f "$SSH_CONFIG.tmp" "$SSH_CONFIG"
  echo "Added the Include directive to $SSH_CONFIG; backed up old config to $SSH_CONFIG~"
else
  echo "$SSH_CONFIG already includes Lima's ssh configs."
fi
chmod 600 "$SSH_CONFIG"

echo
echo "Done. Try it:"
echo "  claudevm new myproject ~/path/to/project"
echo "  claudevm secrets myproject   # optional: GitHub deploy key + Claude token"
echo "  claudevm up myproject"
echo "  claudevm code myproject"
