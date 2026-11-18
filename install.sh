#!/usr/bin/env bash
#
# install.sh: set up claudevm on this host (macOS or Linux).
#
# Safe to re-run: it overwrites the shared template file but never touches
# your per-project instances under ~/.local/var/claudevm/instances/.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDEVM_HOME="${CLAUDEVM_HOME:-$HOME/.config/claudevm}"
# Overridable so tests can stand in for the device; claudevm reads the same
# variable.
KVM_DEVICE="${CLAUDEVM_KVM_DEVICE:-/dev/kvm}"
HOST_OS="$(uname -s)"

brew_install_if_missing() {
  local cmd="$1" formula="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    return
  fi
  if ! command -v brew >/dev/null 2>&1; then
    echo "$cmd not found and Homebrew isn't available." >&2
    echo "Install Homebrew first (https://brew.sh), then run: brew install $formula" >&2
    exit 1
  fi
  echo "$cmd not found. Installing $formula via Homebrew..."
  brew install "$formula"
}

echo "==> Checking dependencies"
if [ "$HOST_OS" = "Darwin" ]; then
  brew_install_if_missing limactl lima
  brew_install_if_missing jq jq
else
  # On Linux this script only reports what is missing: installing system
  # packages needs sudo, and the commands differ by distro.
  qemu="qemu-system-$(uname -m)"
  missing=""
  dnf_packages=""
  need_lima=0
  need_kvm=0
  if ! command -v limactl >/dev/null 2>&1; then
    missing="$missing limactl"
    need_lima=1
  fi
  if ! command -v "$qemu" >/dev/null 2>&1; then
    missing="$missing $qemu"
    # qemu-kvm pulls in the host-arch emulator and its firmware; Lima also
    # needs qemu-img to create disks.
    dnf_packages="$dnf_packages qemu-kvm qemu-img"
  fi
  if ! command -v jq >/dev/null 2>&1; then
    missing="$missing jq"
    dnf_packages="$dnf_packages jq"
  fi
  if [ ! -r "$KVM_DEVICE" ] || [ ! -w "$KVM_DEVICE" ]; then
    missing="$missing $KVM_DEVICE"
    need_kvm=1
  fi

  if [ -n "$missing" ]; then
    echo "Missing:$missing" >&2
    if [ "$need_lima" -eq 1 ]; then
      # Fedora does not package Lima.
      echo "Install Lima from https://lima-vm.io/docs/installation/" >&2
    fi
    if [ -n "$dnf_packages" ] && command -v dnf >/dev/null 2>&1; then
      echo "Install the rest with: sudo dnf install$dnf_packages" >&2
    fi
    if [ "$need_kvm" -eq 1 ]; then
      echo "$KVM_DEVICE must exist and be readable and writable by you: enable" >&2
      echo "virtualization in your firmware settings, and if the device exists," >&2
      echo "run 'sudo usermod -aG kvm \$USER' and log in again." >&2
    fi
    echo "Nothing was installed. Re-run ./install.sh once these are in place." >&2
    exit 1
  fi
fi
echo "Found $(limactl --version)"

if ! command -v code >/dev/null 2>&1; then
  echo "Note: the 'code' CLI isn't on your PATH yet."
  if [ "$HOST_OS" = "Darwin" ]; then
    echo "  In VS Code: Cmd+Shift+P -> 'Shell Command: Install code command in PATH'"
  fi
  echo "  (Only needed for 'claudevm code'; everything else works without it.)"
fi

echo "==> Installing the template to $CLAUDEVM_HOME"
mkdir -p "$CLAUDEVM_HOME"
cp "$REPO_DIR/claude-sandbox.yaml" "$CLAUDEVM_HOME/"

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
    echo "NOTE: $BIN_DIR is not on your PATH. Add this to your shell's startup file"
    echo "(~/.zshrc for zsh, ~/.bashrc for bash):"
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
echo "  claudevm secrets myproject   # Claude token, optional GitHub token"
echo "  claudevm up myproject"
echo "  claudevm code myproject"
