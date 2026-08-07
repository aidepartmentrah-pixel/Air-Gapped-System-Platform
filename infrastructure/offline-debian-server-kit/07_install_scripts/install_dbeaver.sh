#!/usr/bin/env bash
# Installs DBeaver Community Edition from the local .deb package.
# Uses local files only — never touches the internet.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(dirname "$SCRIPT_DIR")"
DEB_FILE="$KIT_ROOT/04_database_tools/dbeaver/dbeaver-ce_26.1.2_amd64.deb"

echo "== Installing DBeaver Community Edition =="

if [ ! -f "$DEB_FILE" ]; then
  echo "ERROR: expected package not found: $DEB_FILE"
  exit 1
fi

echo "DBeaver ships with its own bundled Java runtime — no extra dependencies needed."
echo "Installing $DEB_FILE ..."
sudo dpkg -i "$DEB_FILE"

# DBeaver normally auto-downloads JDBC driver jars from Maven Central the
# first time you connect to a given database type — which fails outright on
# an air-gapped machine. Pre-populate its local driver cache so it never
# needs to try.
#
# DBeaver itself always runs as the regular desktop user, never as root, even
# though this script needs sudo for the .deb install — so we must resolve the
# real (non-root) user's home directory, and fix ownership afterward (same
# class of issue as the pgAdmin/sqlserver permission bugs found during
# offline validation: files created as root are unreadable by the real
# runtime user).
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
DRIVER_CACHE="$REAL_HOME/.local/share/DBeaverData/drivers/maven/maven-central"

echo
echo "Pre-populating JDBC drivers so DBeaver never needs internet access on first connect..."

# Microsoft SQL Server JDBC driver.
# NOTE: DBeaver 26.1.2's bundled driver catalog requests version 14.4.0.jre11,
# which does not exist on Maven Central as of this kit's build date (2026-07)
# — the latest real release is 13.4.0.jre11. We ship the real 13.4.0.jre11
# jar and place a copy at BOTH the real version path and the (currently
# nonexistent) 14.4.0.jre11 path DBeaver's catalog expects, so DBeaver finds
# a cached file and skips the download regardless of which version string it
# asks for. The driver's JDBC surface is stable across this version range for
# standard connectivity. If a future DBeaver update changes the expected
# version again, re-copy the jar under the new expected version string.
MSSQL_DIR_REAL="$DRIVER_CACHE/com/microsoft/sqlserver/mssql-jdbc/13.4.0.jre11"
MSSQL_DIR_EXPECTED="$DRIVER_CACHE/com/microsoft/sqlserver/mssql-jdbc/14.4.0.jre11"
sudo -u "$REAL_USER" mkdir -p "$MSSQL_DIR_REAL" "$MSSQL_DIR_EXPECTED"
sudo -u "$REAL_USER" cp "$KIT_ROOT/04_database_tools/dbeaver/drivers/mssql-jdbc-13.4.0.jre11.jar" "$MSSQL_DIR_REAL/mssql-jdbc-13.4.0.jre11.jar"
sudo -u "$REAL_USER" cp "$KIT_ROOT/04_database_tools/dbeaver/drivers/mssql-jdbc-13.4.0.jre11.jar" "$MSSQL_DIR_EXPECTED/mssql-jdbc-14.4.0.jre11.jar"

# PostgreSQL JDBC driver.
PG_VERSION="42.7.13"
PG_DIR="$DRIVER_CACHE/org/postgresql/postgresql/$PG_VERSION"
sudo -u "$REAL_USER" mkdir -p "$PG_DIR"
sudo -u "$REAL_USER" cp "$KIT_ROOT/04_database_tools/dbeaver/drivers/postgresql-$PG_VERSION.jar" "$PG_DIR/postgresql-$PG_VERSION.jar"

echo "JDBC drivers pre-populated at $DRIVER_CACHE"
echo "DBeaver installed. Launch it from the applications menu, or run: dbeaver-ce"
echo "See 08_documentation/DBEAVER_GUIDE.md for how to connect to SQL Server / PostgreSQL."
