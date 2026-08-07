# Offline Debian Server Kit — RAH Lab

## What this is

Everything needed to turn a brand-new **offline** Debian 13 (trixie), amd64 server into a
host ready for hospital application Docker containers (SQL Server or PostgreSQL) — with
**no internet access required on that server**.

Docker Engine is assumed to already be installed on the target server. This kit does
**not** install or download Docker. It only verifies it.

## Read order

1. `01_verify_docker/DOCKER_VERIFY_GUIDE.md` — confirm Docker is healthy before anything else.
2. `08_documentation/OFFLINE_SERVER_INSTALL_MANUAL.md` — the main step-by-step install walkthrough.
3. Run `07_install_scripts/install_everything.sh` (or follow the manual steps by hand).
4. Run `07_install_scripts/verify_everything.sh` to confirm the server is ready.
5. `09_verification/VALIDATION_CHECKLIST.md` — final sign-off checklist before handing the
   server over for a hospital application release.

## Folder map

| Folder | Contents |
|---|---|
| `01_verify_docker/` | Docker verification procedure only (no installer) |
| `02_portainer/` | Portainer CE Docker image (.tar) |
| `03_database_images/` | SQL Server and PostgreSQL Docker images (.tar) |
| `04_database_tools/` | DBeaver Community Edition installer |
| `05_documentation_tools/` | Obsidian installer |
| `06_utilities/` | CLI tool `.deb` packages (git, curl, wget, htop, nano, vim, rsync, zip, unzip, tmux, tree) + dependencies |
| `07_install_scripts/` | All install/verify shell scripts — local files only, no network access |
| `08_documentation/` | Full manuals, written for an operator with limited Linux experience |
| `09_verification/` | Final validation checklist |
| `10_remote_desktop/` | xrdp `.deb` package + dependencies (assumes a desktop environment already exists on the target) |
| `CHECKSUMS.txt` | SHA-256 checksums for every file in this kit, to verify integrity after USB/DVD transfer |

## Ground rules baked into every script

- Never touches the internet.
- Never assumes anything beyond what is physically inside this folder.
- Stops immediately and prints a clear error on any failure (no silent partial installs).
- SQL Server edition (Express, by default in this kit) is chosen at **container runtime**
  via the `MSSQL_PID` environment variable — it is the same Docker image for every edition.
  See `08_documentation/SQLSERVER_CONTAINER_GUIDE.md`.
