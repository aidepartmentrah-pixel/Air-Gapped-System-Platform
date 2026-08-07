#!/usr/bin/env bash
# RAH-OIP 1.0.0 — full install orchestrator.
# Configures the curated local APT repository, then lets the real apt/dpkg solver
# install every OS-level component. Uses local files only — no internet required
# or attempted at any point.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_ROOT="$(dirname "$SCRIPT_DIR")"
APT_REPO_ROOT="$RELEASE_ROOT/01_APT_Repository"
IMAGES_DIR="$RELEASE_ROOT/03_Docker_Images"
LOG_DIR="$RELEASE_ROOT/install_logs"
mkdir -p "$LOG_DIR"

step() { echo; echo "=================================================="; echo " $1"; echo "=================================================="; }

step "Step 1/6: Configuring curated local APT repository (internet sources disabled)"
if [ ! -f "$APT_REPO_ROOT/Packages" ]; then
  echo "ERROR: $APT_REPO_ROOT/Packages not found. Release is incomplete."
  exit 1
fi
# Disable the machine's default (internet) apt sources for the duration of this
# install so any gap in the curated repo fails loudly instead of silently
# succeeding via a fallback that will not exist on the real air-gapped target.
if [ -f /etc/apt/sources.list ] && [ ! -f /etc/apt/sources.list.rah-oip-disabled ]; then
  sudo mv /etc/apt/sources.list /etc/apt/sources.list.rah-oip-disabled
fi
for f in /etc/apt/sources.list.d/*.list; do
  [ -f "$f" ] || continue
  case "$f" in
    */rah-oip-local.list) ;;
    *) sudo mv "$f" "$f.rah-oip-disabled" 2>/dev/null || true ;;
  esac
done
# NOTE: sources.list URI must point at APT_REPO_ROOT (the parent of pool/), not
# pool/ itself — dpkg-scanpackages recorded Filename entries as "pool/<file>.deb"
# relative to APT_REPO_ROOT. Pointing directly at pool/ causes apt to look for a
# nonexistent doubly-nested "pool/pool/<file>.deb" path.
echo "deb [trusted=yes] file://$APT_REPO_ROOT ./" | sudo tee /etc/apt/sources.list.d/rah-oip-local.list >/dev/null
sudo apt-get update 2>&1 | tee "$LOG_DIR/01_apt_update.log"

step "Step 2/6: Installing Docker Engine + Compose"
sudo apt-get -y --no-install-recommends install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  2>&1 | tee "$LOG_DIR/02_docker_install.log"
sudo systemctl enable docker
sudo systemctl restart docker
sudo usermod -aG docker "$USER" || true

step "Step 3/6: Installing xrdp + xorgxrdp (remote desktop)"
sudo apt-get -y --no-install-recommends install xrdp xorgxrdp 2>&1 | tee "$LOG_DIR/03_xrdp_install.log"
sudo systemctl enable xrdp
sudo systemctl restart xrdp

step "Step 4/6: Installing DBeaver + Obsidian"
sudo apt-get -y --no-install-recommends install dbeaver-ce obsidian 2>&1 | tee "$LOG_DIR/04_tools_install.log"

step "Step 5/6: Installing CLI utilities"
sudo apt-get -y --no-install-recommends install git curl wget htop nano vim rsync zip unzip tmux tree \
  2>&1 | tee "$LOG_DIR/05_utilities_install.log"

step "Step 6/6: Loading Docker images and starting Portainer"
sudo docker load -i "$IMAGES_DIR/mssql-server-2022-pinned.tar" 2>&1 | tee "$LOG_DIR/06_load_mssql.log"
sudo docker load -i "$IMAGES_DIR/postgres-16.14.tar" 2>&1 | tee -a "$LOG_DIR/06_load_mssql.log"
sudo docker load -i "$IMAGES_DIR/portainer-ce-dd43259.tar" 2>&1 | tee -a "$LOG_DIR/06_load_mssql.log"

if ! sudo docker ps -a --format '{{.Names}}' | grep -qx portainer; then
  sudo docker volume create portainer_data >/dev/null
  sudo docker run -d --name portainer --restart unless-stopped \
    -p 9443:9443 -p 8000:8000 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v portainer_data:/data \
    portainer/portainer-ce:dd43259
fi

echo
echo "=================================================="
echo " Install sequence complete. Run 08_Verification/verify_everything.sh next."
echo "=================================================="
