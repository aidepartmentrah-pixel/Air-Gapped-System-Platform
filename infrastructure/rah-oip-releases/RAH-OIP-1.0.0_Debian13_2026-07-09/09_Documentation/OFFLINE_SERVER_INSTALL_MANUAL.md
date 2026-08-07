# Offline Server Install Manual — RAH-OIP 1.0.0

Audience: an IT operator with limited Linux experience, working on a Debian 13
(trixie), amd64 server with **no internet access**.

## Before you start

1. Copy this whole release folder (`RAH-OIP-1.0.0_Debian13_2026-07-09/`) onto
   the offline server, e.g. to `/home/<user>/RAH-OIP-1.0.0_Debian13_2026-07-09`.
2. Verify the copy is intact:
   ```
   cd RAH-OIP-1.0.0_Debian13_2026-07-09
   sha256sum -c CHECKSUMS.txt
   ```
   Every line should end in `OK`. If any say `FAILED`, re-copy the release —
   do not attempt to install a corrupted transfer.

## Installing

```
bash 07_Installation/install_everything.sh
```

This single script:
1. Registers the release's curated APT repository (`01_APT_Repository/`) as
   the system's only package source — the machine's default internet sources
   are temporarily disabled for the duration of the install, so any missing
   package fails loudly instead of silently trying (and failing) to reach the
   internet.
2. Installs Docker Engine, Compose, and Buildx.
3. Installs xrdp + xorgxrdp (remote desktop).
4. Installs DBeaver and Obsidian.
5. Installs CLI utilities (git, curl, wget, htop, nano, vim, rsync, zip,
   unzip, tmux, tree).
6. Loads the SQL Server, PostgreSQL, and Portainer Docker images, and starts
   Portainer.

The script requires `sudo` — you'll be prompted for your password once per
step (or prime it up front with `sudo -v`).

It stops immediately if any step fails, and every step's output is logged to
`install_logs/` inside the release folder for troubleshooting.

## Verifying

```
bash 08_Verification/verify_everything.sh
```

Expected: a list of `[ OK ]` lines ending in `ALL CHECKS PASSED.` If anything
shows `[FAIL]`, check the matching log in `install_logs/`.

## What "ready" means

Once verification passes, this server has:
- Docker + Compose, ready to run application containers
- Portainer at `https://<server-ip>:9443` for managing containers
- SQL Server and PostgreSQL images loaded (start containers as needed — see
  each database's guide for exact `docker run` invocations and `MSSQL_PID`
  edition selection)
- DBeaver and Obsidian installed
- xrdp running — connect via Windows Remote Desktop Connection to
  `<server-ip>:3389`
- All required CLI utilities installed

This server is now ready to receive an application's release package
(Dockerfiles, docker-compose.yml, database install scripts).

## If something goes wrong

Check `install_logs/<step>.log` for the exact `apt`/`docker` output. Since the
release disables internet apt sources during install, any "unable to fetch"
error means a package is genuinely missing from this release's curated
repository — this is a release defect to report, not something to work around
by manually re-enabling internet sources on the production server.
