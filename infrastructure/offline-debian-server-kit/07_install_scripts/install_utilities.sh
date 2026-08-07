#!/usr/bin/env bash
# Installs the CLI utility packages (git, curl, wget, htop, nano, vim, rsync, zip,
# unzip, tmux, tree) and their full dependency closure from local .deb files.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"
DEB_DIR="$KIT_ROOT/06_utilities/deb-packages"

echo "== Installing CLI utilities =="

if [ ! -d "$DEB_DIR" ] || ! compgen -G "$DEB_DIR"/*.deb >/dev/null; then
  echo "ERROR: no .deb packages found in $DEB_DIR"
  exit 1
fi

count=$(ls "$DEB_DIR"/*.deb | wc -l)
echo "Installing $count package(s) from $DEB_DIR ..."
sudo dpkg -i "$DEB_DIR"/*.deb

echo
echo "Utilities installed. Verifying each tool responds:"
for tool in git curl wget htop nano vim rsync zip unzip tmux tree; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "  [ OK ] $tool"
  else
    echo "  [FAIL] $tool not found on PATH"
  fi
done
