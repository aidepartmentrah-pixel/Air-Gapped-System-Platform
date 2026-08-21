#!/bin/sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="$(dirname "$SCRIPT_DIR")"
docker load -i "$RELEASE_DIR/docker-images/backend.tar"
docker compose -f "$RELEASE_DIR/compose/docker-compose.yml" --env-file "$RAH_ACTIVE_DEPLOYMENT_PATH/compose/.env" -p rah-health-fail-app up -d
