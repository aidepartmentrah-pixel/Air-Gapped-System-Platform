#!/usr/bin/env bash
# Installs Obsidian and its dependency packages from local .deb files.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"
OBSIDIAN_DIR="$KIT_ROOT/05_documentation_tools/obsidian"
DEB_FILE="$OBSIDIAN_DIR/obsidian_1.12.7_amd64.deb"
DEPS_DIR="$OBSIDIAN_DIR/deps"

echo "== Installing Obsidian =="

if [ ! -f "$DEB_FILE" ]; then
  echo "ERROR: expected package not found: $DEB_FILE"
  exit 1
fi

if [ -d "$DEPS_DIR" ] && compgen -G "$DEPS_DIR"/*.deb >/dev/null; then
  echo "Installing Obsidian's dependency packages first..."
  sudo dpkg -i "$DEPS_DIR"/*.deb || true
fi

echo "Installing Obsidian..."
sudo dpkg -i "$DEB_FILE"

echo
echo "Obsidian installed. Launch it from the applications menu, or run: obsidian"
echo "See 08_documentation/OBSIDIAN_GUIDE.md for first-time vault setup."
