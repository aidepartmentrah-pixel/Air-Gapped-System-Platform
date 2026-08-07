#!/usr/bin/env bash
# Installs xrdp + xorgxrdp (RDP remote desktop server + Xorg session driver) and every
# dependency from local .deb files. Assumes a desktop environment (Xorg-based) is already
# installed on this server. Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"
DEB_DIR="$KIT_ROOT/10_remote_desktop"

echo "== Installing xrdp (Remote Desktop) =="

if [ ! -d "$DEB_DIR" ] || ! compgen -G "$DEB_DIR"/*.deb >/dev/null; then
  echo "ERROR: no .deb packages found in $DEB_DIR"
  exit 1
fi

count=$(ls "$DEB_DIR"/*.deb | wc -l)
echo "Installing $count package(s) from $DEB_DIR ..."
sudo dpkg -i "$DEB_DIR"/*.deb

echo "Enabling and starting the xrdp service..."
sudo systemctl enable xrdp
sudo systemctl restart xrdp

echo
if systemctl is-active --quiet xrdp; then
  echo "xrdp is installed and running."
  echo "Connect from a Windows machine using Remote Desktop Connection (mstsc) to:"
  echo "  $(hostname -I | awk '{print $1}'):3389"
else
  echo "WARNING: xrdp did not start. Run: sudo systemctl status xrdp --no-pager"
fi
echo "See 08_documentation/XRDP_GUIDE.md for desktop-environment-specific setup notes."
