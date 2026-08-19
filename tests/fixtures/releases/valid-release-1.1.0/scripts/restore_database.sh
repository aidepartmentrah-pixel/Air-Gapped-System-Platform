#!/bin/sh
set -e
: "${RAH_BACKUP_SOURCE_PATH:?RAH_BACKUP_SOURCE_PATH not set}"
: "${RAH_ACTIVE_DEPLOYMENT_PATH:?RAH_ACTIVE_DEPLOYMENT_PATH not set}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="$(dirname "$SCRIPT_DIR")"
cp "$RAH_BACKUP_SOURCE_PATH" "$RAH_ACTIVE_DEPLOYMENT_PATH/compose/.env"
docker load -i "$RELEASE_DIR/docker-images/backend.tar"
docker compose --env-file "$RAH_ACTIVE_DEPLOYMENT_PATH/compose/.env" -f "$RELEASE_DIR/compose/docker-compose.yml" -p rah-golden-test-app up -d
