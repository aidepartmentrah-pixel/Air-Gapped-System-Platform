#!/usr/bin/env bash
# Verifies Docker Engine is installed and healthy. Does NOT install or download anything.
set -euo pipefail

PASS="[ OK ]"
FAIL="[FAIL]"
failures=0

check() {
  local description="$1"
  shift
  if "$@" >/tmp/verify_docker_check.log 2>&1; then
    echo "$PASS  $description"
  else
    echo "$FAIL  $description"
    sed 's/^/       /' /tmp/verify_docker_check.log
    failures=$((failures + 1))
  fi
}

echo "== Docker Verification =="
echo

echo "-- Step 1: Docker version --"
check "docker --version" docker --version

echo
echo "-- Step 2: Docker service is running --"
check "systemctl status docker (active)" bash -c "systemctl is-active --quiet docker"

echo
echo "-- Step 3: Docker daemon responds --"
check "docker info" docker info

echo
echo "-- Step 4: Docker Compose plugin present --"
check "docker compose version" docker compose version

echo
echo "-- Step 5: Docker runs without sudo --"
check "docker ps" docker ps

echo
echo "-- Step 6: Disk space under /var/lib/docker --"
avail_kb=$(df --output=avail /var/lib/docker 2>/dev/null | tail -n1 | tr -d ' ')
if [ -n "${avail_kb:-}" ] && [ "$avail_kb" -ge $((20 * 1024 * 1024)) ]; then
  echo "$PASS  At least 20 GB free under /var/lib/docker"
else
  echo "$FAIL  Less than 20 GB free under /var/lib/docker"
  failures=$((failures + 1))
fi

echo
if [ "$failures" -eq 0 ]; then
  echo "All Docker checks passed. Safe to continue with the rest of this kit."
  exit 0
else
  echo "$failures check(s) failed. See 08_documentation/TROUBLESHOOTING.md before continuing."
  exit 1
fi
