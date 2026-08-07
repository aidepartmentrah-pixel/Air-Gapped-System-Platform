#!/usr/bin/env bash
# Verifies the offline server is fully ready: Docker, Portainer, loaded database
# images, DBeaver, Obsidian, utilities, disk space, RAM, and container networking.
set -uo pipefail

PASS="[ OK ]"
FAIL="[FAIL]"
failures=0

pass() { echo "$PASS  $1"; }
fail() { echo "$FAIL  $1"; failures=$((failures + 1)); }

echo "== Full System Verification =="

echo
echo "-- Docker --"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  pass "Docker daemon is running"
else
  fail "Docker daemon is not reachable"
fi

echo
echo "-- Portainer --"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "portainer"; then
  pass "Portainer container is running"
else
  fail "Portainer container is not running"
fi

echo
echo "-- Database images loaded --"
if docker images --format '{{.Repository}}' 2>/dev/null | grep -qx "mcr.microsoft.com/mssql/server"; then
  pass "SQL Server image is loaded"
else
  fail "SQL Server image is not loaded"
fi
if docker images --format '{{.Repository}}' 2>/dev/null | grep -qx "postgres"; then
  pass "PostgreSQL image is loaded"
else
  fail "PostgreSQL image is not loaded"
fi

echo
echo "-- DBeaver --"
if command -v dbeaver-ce >/dev/null 2>&1 || dpkg -s dbeaver-ce >/dev/null 2>&1; then
  pass "DBeaver is installed"
else
  fail "DBeaver is not installed"
fi

echo
echo "-- Obsidian --"
if command -v obsidian >/dev/null 2>&1 || dpkg -s obsidian >/dev/null 2>&1; then
  pass "Obsidian is installed"
else
  fail "Obsidian is not installed"
fi

echo
echo "-- CLI utilities --"
for tool in git curl wget htop nano vim rsync zip unzip tmux tree; do
  if command -v "$tool" >/dev/null 2>&1; then
    pass "$tool is installed"
  else
    fail "$tool is missing"
  fi
done

echo
echo "-- xrdp (remote desktop) --"
if systemctl is-active --quiet xrdp 2>/dev/null; then
  pass "xrdp service is running"
else
  fail "xrdp service is not running"
fi
if dpkg -s xorgxrdp >/dev/null 2>&1; then
  pass "xorgxrdp is installed"
else
  fail "xorgxrdp is not installed"
fi

echo
echo "-- Disk space --"
avail_kb=$(df --output=avail / 2>/dev/null | tail -n1 | tr -d ' ')
if [ -n "${avail_kb:-}" ] && [ "$avail_kb" -ge $((20 * 1024 * 1024)) ]; then
  pass "At least 20 GB free on /"
else
  fail "Less than 20 GB free on /"
fi

echo
echo "-- RAM --"
total_mem_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
if [ "$total_mem_kb" -ge $((4 * 1024 * 1024)) ]; then
  pass "At least 4 GB RAM detected"
else
  fail "Less than 4 GB RAM detected"
fi

echo
echo "-- Container networking --"
if docker network ls >/dev/null 2>&1; then
  pass "Docker networking is functional"
else
  fail "Docker networking check failed"
fi

echo
if [ "$failures" -eq 0 ]; then
  echo "ALL CHECKS PASSED. Server is ready for hospital application release packages."
  exit 0
else
  echo "$failures check(s) failed. See 08_documentation/TROUBLESHOOTING.md and"
  echo "09_verification/VALIDATION_CHECKLIST.md before proceeding."
  exit 1
fi
