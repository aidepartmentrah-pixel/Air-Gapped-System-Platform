# Image & Package Versions in This Kit

Built on: 2026-07-07, from an online Debian 13 (trixie) amd64 VM.

## Docker images

| Component | Tag used in this kit | Resolved digest at pull time |
|---|---|---|
| Portainer CE | `portainer/portainer-ce:dd43259` | `sha256:5f9b4bda5582fc72c07d730f86168205f4042d82c9cde011c9146b12496e4625` |
| SQL Server | `mcr.microsoft.com/mssql/server:2022-pinned` | `sha256:e07b9699a2b749969f19d86563ceeea22bd3a69f7f1db85a8d1ac4bdaf0c6f56` |
| PostgreSQL | `postgres:16.14` | `sha256:fe03a7605299a34ddf5e4f285dff78c3d7190a576b3c6b46f2fcff69f4bffd54` |

The local tags above (`dd43259`, `2022-pinned`) were applied on the build VM purely so the
saved `.tar` filenames are meaningful — they are not upstream release names. The digest is
the authoritative identifier if you need to confirm exactly which build this is.

## Other packages

| Component | Version | Source |
|---|---|---|
| DBeaver CE | 26.1.2 | `dbeaver.io/files/dbeaver-ce_latest_amd64.deb` at build time |
| Obsidian | 1.12.7 | GitHub releases, `obsidianmd/obsidian-releases` |
| CLI utilities | Debian 13 (trixie) repo versions as of build date | `deb.debian.org` |

## Rebuilding this kit later

To pick up newer versions in a future kit build, re-run the same pull/download commands
on a current online VM — do not hand-edit version numbers in this file without also
re-downloading the corresponding files.
