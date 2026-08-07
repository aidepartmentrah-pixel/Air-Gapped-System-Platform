# Compatibility Matrix — RAH-OIP 1.0.0

| Component | Version | Notes |
|---|---|---|
| Target OS | Debian 13 (trixie), amd64 | Must match exactly — the curated repo is built from a trixie package set |
| Docker Engine | 5:29.6.1-1~debian.13~trixie | From Docker's official apt repo, mirrored into the curated repository |
| Docker Compose plugin | 5.3.1-1~debian.13~trixie | |
| Docker Buildx plugin | 0.35.0-1~debian.13~trixie | |
| containerd | 2.2.5-1~debian.13~trixie | |
| Portainer CE | local tag `dd43259` | Digest: `sha256:5f9b4bda5582fc72c07d730f86168205f4042d82c9cde011c9146b12496e4625` |
| SQL Server | local tag `2022-pinned` | Digest: `sha256:e07b9699a2b749969f19d86563ceeea22bd3a69f7f1db85a8d1ac4bdaf0c6f56`. Edition (Express by default) chosen at container runtime via `MSSQL_PID` |
| PostgreSQL | 16.14 | Digest: `sha256:fe03a7605299a34ddf5e4f285dff78c3d7190a576b3c6b46f2fcff69f4bffd54` |
| DBeaver CE | 26.1.2 | No external dependencies (bundles its own JRE) |
| Obsidian | 1.12.7 | Requires the `libgtk-3-0`/`libatspi2.0-0` compatibility shims included in this release (see Known Issues) |
| xrdp | 0.10.1-3.1+deb13u1 | |
| xorgxrdp | 1:0.10.2-1 | Requires an Xorg-based desktop already installed on the target |

## Validated Against

- **Environment:** Offline-AirGapped-Simulator (Hyper-V, Debian 13 trixie amd64, no internet)
- **Result:** PASSED — see `VALIDATION_REPORT.md`

## Known Incompatibilities

- xrdp + GNOME Shell: not reliably supported (upstream xrdp/GNOME Wayland limitation). XFCE and KDE Plasma confirmed to work with xrdp in general Debian usage; not independently re-tested in this release's validation cycle.
