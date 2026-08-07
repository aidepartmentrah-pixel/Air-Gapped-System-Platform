#!/usr/bin/env bash
# Loads the Portainer CE image from a local tar file and starts it as a container.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"
PORTAINER_TAR="$KIT_ROOT/02_portainer/portainer-ce-dd43259.tar"
IMAGE_TAG="portainer/portainer-ce:dd43259"
CONTAINER_NAME="portainer"

echo "== Installing Portainer CE =="

if [ ! -f "$PORTAINER_TAR" ]; then
  echo "ERROR: expected image file not found: $PORTAINER_TAR"
  exit 1
fi

echo "Loading Portainer image ($(du -h "$PORTAINER_TAR" | cut -f1))..."
docker load -i "$PORTAINER_TAR"

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "A container named '$CONTAINER_NAME' already exists. Skipping creation."
  echo "To recreate it: docker rm -f $CONTAINER_NAME   then re-run this script."
else
  echo "Creating Portainer volume for persistent data..."
  docker volume create portainer_data >/dev/null

  echo "Starting Portainer container..."
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p 9443:9443 \
    -p 8000:8000 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v portainer_data:/data \
    "$IMAGE_TAG"
fi

echo
echo "Portainer is starting. Open https://<server-ip>:9443 in a browser to finish setup."
echo "See 08_documentation/PORTAINER_GUIDE.md for the full walkthrough."
