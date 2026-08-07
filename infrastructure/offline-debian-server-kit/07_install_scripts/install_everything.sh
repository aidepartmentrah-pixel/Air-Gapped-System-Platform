#!/usr/bin/env bash
# Runs the full offline install sequence in order. Stops immediately on any failure.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_step() {
  local description="$1"
  local script="$2"
  echo
  echo "=================================================="
  echo " $description"
  echo "=================================================="
  bash "$SCRIPT_DIR/$script"
}

run_step "Step 1/7: Verifying Docker" "verify_docker.sh"
run_step "Step 2/7: Loading database images (SQL Server, PostgreSQL)" "load_database_images.sh"
run_step "Step 3/7: Installing Portainer" "install_portainer.sh"
run_step "Step 4/7: Installing DBeaver" "install_dbeaver.sh"
run_step "Step 5/7: Installing Obsidian" "install_obsidian.sh"
run_step "Step 6/7: Installing CLI utilities" "install_utilities.sh"
run_step "Step 7/7: Installing xrdp (remote desktop)" "install_xrdp.sh"

echo
echo "=================================================="
echo " All install steps completed successfully."
echo " Run verify_everything.sh to confirm the server is ready."
echo "=================================================="
