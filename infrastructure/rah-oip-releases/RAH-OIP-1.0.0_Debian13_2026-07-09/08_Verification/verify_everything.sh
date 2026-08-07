#!/usr/bin/env bash
# RAH-OIP 1.0.0 — full verification pass.
set -uo pipefail

PASS="[ OK ]"; FAIL="[FAIL]"; failures=0
pass() { echo "$PASS  $1"; }
fail() { echo "$FAIL  $1"; failures=$((failures + 1)); }

echo "== RAH-OIP 1.0.0 Full Verification =="

echo; echo "-- No internet access (expected on air-gapped target) --"
if timeout 3 curl -sI https://deb.debian.org >/dev/null 2>&1; then
  fail "Internet is reachable (unexpected for air-gapped target)"
else
  pass "No internet reachable (correct for air-gapped target)"
fi

echo; echo "-- Docker --"
command -v docker >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1 && pass "Docker daemon is running" || fail "Docker daemon is not reachable"
sudo docker compose version >/dev/null 2>&1 && pass "Docker Compose plugin present" || fail "Docker Compose plugin missing"

echo; echo "-- Portainer --"
sudo docker ps --format '{{.Names}}' 2>/dev/null | grep -qx portainer && pass "Portainer container running" || fail "Portainer container not running"

echo; echo "-- Database images --"
sudo docker images --format '{{.Repository}}' 2>/dev/null | grep -qx "mcr.microsoft.com/mssql/server" && pass "SQL Server image loaded" || fail "SQL Server image missing"
sudo docker images --format '{{.Repository}}' 2>/dev/null | grep -qx "postgres" && pass "PostgreSQL image loaded" || fail "PostgreSQL image missing"

echo; echo "-- DBeaver / Obsidian --"
dpkg -s dbeaver-ce >/dev/null 2>&1 && pass "DBeaver installed" || fail "DBeaver not installed"
dpkg -s obsidian >/dev/null 2>&1 && pass "Obsidian installed" || fail "Obsidian not installed"

echo; echo "-- xrdp --"
systemctl is-active --quiet xrdp && pass "xrdp service running" || fail "xrdp service not running"
dpkg -s xorgxrdp >/dev/null 2>&1 && pass "xorgxrdp installed" || fail "xorgxrdp not installed"

echo; echo "-- CLI utilities --"
for tool in git curl wget htop nano vim rsync zip unzip tmux tree; do
  command -v "$tool" >/dev/null 2>&1 && pass "$tool installed" || fail "$tool missing"
done

echo
if [ "$failures" -eq 0 ]; then
  echo "ALL CHECKS PASSED."
  exit 0
else
  echo "$failures check(s) FAILED."
  exit 1
fi
