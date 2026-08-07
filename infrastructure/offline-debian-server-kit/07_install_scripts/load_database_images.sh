#!/usr/bin/env bash
# Loads the SQL Server and PostgreSQL Docker images from local tar files.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"

SQLSERVER_TAR="$KIT_ROOT/03_database_images/sqlserver/mssql-server-2022-pinned.tar"
POSTGRES_TAR="$KIT_ROOT/03_database_images/postgres/postgres-16.14.tar"

echo "== Loading database Docker images =="

for tar_file in "$SQLSERVER_TAR" "$POSTGRES_TAR"; do
  if [ ! -f "$tar_file" ]; then
    echo "ERROR: expected image file not found: $tar_file"
    exit 1
  fi
done

echo "Loading SQL Server image ($(du -h "$SQLSERVER_TAR" | cut -f1))..."
docker load -i "$SQLSERVER_TAR"

echo "Loading PostgreSQL image ($(du -h "$POSTGRES_TAR" | cut -f1))..."
docker load -i "$POSTGRES_TAR"

echo
echo "Loaded images now available:"
docker images --filter "reference=mcr.microsoft.com/mssql/server" --filter "reference=postgres"

echo
echo "Database images loaded successfully."
echo "SQL Server edition is chosen at container run time via the MSSQL_PID environment"
echo "variable — see 08_documentation/SQLSERVER_CONTAINER_GUIDE.md."
