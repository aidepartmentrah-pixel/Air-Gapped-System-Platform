# RAH-OIP 1.0.0 — Release Notes

**Release date:** 2026-07-09
**Target:** Debian 13 (trixie), amd64

## What this release is

The first fully validated Infrastructure Release under the RAH Offline
Infrastructure Platform standard. Replaces the earlier ad hoc
`offline-debian-server-kit` approach (loose, manually-curated `.deb` files)
with a real curated local APT repository, so the target's own `apt`/`dpkg`
solver resolves dependencies instead of a hand-computed closure.

## What's included

- Curated local APT repository (312 packages): Docker Engine + Compose +
  Buildx, xrdp + xorgxrdp, DBeaver CE, Obsidian, and CLI utilities (git, curl,
  wget, htop, nano, vim, rsync, zip, unzip, tmux, tree)
- Docker container images: Portainer CE, SQL Server 2022 (Express edition via
  `MSSQL_PID`), PostgreSQL 16.14
- One-shot install orchestrator (`07_Installation/install_everything.sh`) and
  full verification suite (`08_Verification/verify_everything.sh`)

## Why this release exists

Two prior offline-install attempts failed on a clean Debian 13 VM (missing
`libfuse2t64` dependency for xrdp; Docker assumed pre-installed rather than
included). This release fixes both by making the OS package layer a first-class,
versioned part of the platform rather than an assumption about the target.

## Known issues

- xrdp does not reliably support a full GNOME Shell session (upstream
  limitation of xrdp's X11 backend). XFCE and KDE Plasma work normally.
  `xorgxrdp` is included so xrdp attaches to the real desktop session rather
  than falling back to a separate Xvnc session.
- DBeaver's SQL Server / PostgreSQL JDBC drivers must be pre-populated in
  DBeaver's driver cache before first offline use (DBeaver will otherwise try
  to download them on first connection attempt, which will fail offline).

## Validation

See `VALIDATION_REPORT.md` — validated on a clean Hyper-V snapshot
(`GoldenSnapshot-WithNetwork`) with zero manual intervention during the
install/verify run. Final status: **PASSED**.
