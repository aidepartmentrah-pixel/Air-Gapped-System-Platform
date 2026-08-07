# Offline Server Install Manual

Audience: an IT operator with limited Linux experience, working on a Debian 13 (trixie),
amd64 server that has **no internet access**. Docker Engine is already installed on this
server — this manual does not install it.

Everything you need is inside this kit folder. Do not download anything else.

## Before you start

1. Confirm this whole `offline-debian-server-kit` folder has been copied onto the offline
   server (e.g. from USB to `/opt/offline-debian-server-kit` or your home directory).
2. Open a terminal and `cd` into that folder.
3. Verify the copy is intact:
   ```
   sha256sum -c CHECKSUMS.txt
   ```
   Expected output: every line ends in `OK`. If any line says `FAILED`, the file was
   corrupted during transfer — re-copy the kit from the original USB/DVD before continuing.

## Option A — One command install (recommended)

```
bash 07_install_scripts/install_everything.sh
```

This runs, in order:
1. Docker verification
2. Loading the SQL Server and PostgreSQL images
3. Installing Portainer
4. Installing DBeaver
5. Installing Obsidian
6. Installing CLI utilities
7. Installing xrdp (remote desktop access)

The script **stops immediately** if any step fails, and tells you exactly which step
failed. If that happens, open `TROUBLESHOOTING.md` and find the matching section before
re-running.

## Option B — Step by step (if you want to see each stage)

```
bash 07_install_scripts/verify_docker.sh
bash 07_install_scripts/load_database_images.sh
bash 07_install_scripts/install_portainer.sh
bash 07_install_scripts/install_dbeaver.sh
bash 07_install_scripts/install_obsidian.sh
bash 07_install_scripts/install_utilities.sh
bash 07_install_scripts/install_xrdp.sh
```

## After installing — verify everything

```
bash 07_install_scripts/verify_everything.sh
```

Expected: a list of `[ OK ]` lines and a final message:
```
ALL CHECKS PASSED. Server is ready for hospital application release packages.
```

If you see any `[FAIL]` lines, the summary at the bottom tells you how many failed —
resolve each one (see `TROUBLESHOOTING.md`) and re-run the script.

## What "ready" means

Once `verify_everything.sh` passes with zero failures, this server has:

- A running Portainer instance at `https://<server-ip>:9443` for managing containers
- SQL Server and PostgreSQL Docker images loaded and ready to run
- DBeaver installed for connecting to and inspecting databases
- Obsidian installed for viewing/editing documentation
- All required CLI utilities installed
- xrdp running, so operators can connect via Windows Remote Desktop Connection (`mstsc`)
  to `<server-ip>:3389` instead of needing physical console access

This server is now ready to receive an application's release package (Dockerfiles,
docker-compose.yml, database install scripts) produced by the separate Dockerization
prompts (2A for SQL Server projects, 2B for PostgreSQL projects).

## Final sign-off

Complete `09_verification/VALIDATION_CHECKLIST.md` and keep a copy for your records
before handing the server over for application deployment.
