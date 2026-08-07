# Validation Report — RAH-OIP 1.0.0

**Release:** RAH-OIP-1.0.0_Debian13_2026-07-09
**Target OS:** Debian 13 (trixie), amd64
**Validation date:** 2026-07-09
**Validation environment:** Offline-AirGapped-Simulator (Hyper-V VM on Legion workstation, no internet access, internal-only network 10.10.10.0/24)
**Validated by:** Release engineering session (Claude, release engineer: orstt)

## Golden Snapshot

Baseline: `GoldenSnapshot-WithNetwork`, created 2026-07-09 11:27:25, containing:
- Clean Debian 13 (trixie) desktop install
- Static IP 10.10.10.2/24 configured persistently (via NetworkManager connection profile)
- No Docker, no prior RAH-OIP artifacts, no internet access
- SSH access from the Release Engineering Machine (10.10.10.1)

Note: an earlier automatic Hyper-V checkpoint was found to predate the network
configuration and produced a VM with no working network on revert — that
checkpoint is not used as a baseline. `GoldenSnapshot-WithNetwork` is the
correct baseline for all future validation cycles.

## Procedure Executed

1. Reverted `Offline-AirGapped-Simulator` to `GoldenSnapshot-WithNetwork`.
2. Confirmed clean state via SSH: no `docker` binary, no leftover release
   directories, no `/etc/apt/sources.list.d/rah-oip-local.list`, no internet
   reachability.
3. Transferred `RAH-OIP-1.0.0_Debian13_2026-07-09/` (1.3 GB) via SCP.
4. Ran `07_Installation/install_everything.sh` end-to-end with no manual
   intervention — exit code 0, zero `apt` errors.
5. Ran `08_Verification/verify_everything.sh` — all checks passed.

## Installation Results

| Step | Result |
|---|---|
| Configure curated local APT repository (internet sources disabled) | PASS |
| Install Docker Engine + Compose + Buildx | PASS |
| Install xrdp + xorgxrdp | PASS |
| Install DBeaver + Obsidian | PASS |
| Install CLI utilities (git, curl, wget, htop, nano, vim, rsync, zip, unzip, tmux, tree) | PASS |
| Load Docker images (SQL Server, PostgreSQL, Portainer) + start Portainer | PASS |

## Verification Results

| Check | Result |
|---|---|
| No internet reachable (expected) | PASS |
| Docker daemon running | PASS |
| Docker Compose plugin present | PASS |
| Portainer container running | PASS |
| SQL Server image loaded | PASS |
| PostgreSQL image loaded | PASS |
| DBeaver installed | PASS |
| Obsidian installed | PASS |
| xrdp service running | PASS |
| xorgxrdp installed | PASS |
| git, curl, wget, htop, nano, vim, rsync, zip, unzip, tmux, tree installed | PASS (all 11) |

## Issues Found and Fixed During Prior Iterations (not present in this final run)

1. **Percent-encoded filenames** — `apt-get download` saved some packages with
   a literal `%3a` in the filename (epoch separator); `dpkg-scanpackages`
   copied this unescaped into the `Filename:` field, causing apt to
   double-encode and fail to find the file. Fixed by renaming all affected
   files to their real decoded form (literal `:`, valid on Linux filesystems).
2. **Flat-repo path mismatch** — the install script pointed apt's source at
   `01_APT_Repository/pool/` instead of `01_APT_Repository/` (the correct flat
   repository root, since `Packages` records paths as `pool/<file>.deb`
   relative to the parent). Fixed by correcting the `sources.list` entry and
   moving `Packages`/`Packages.gz` to the repository root.
3. **Recommends causing internet fallback** — without `--no-install-recommends`,
   apt pulled in `patch` and `pigz` (Recommends of `docker-ce`, not curated
   into the local repo) and fell back to the machine's default internet apt
   sources, which are unreachable on the real air-gapped target. Fixed by
   adding `--no-install-recommends` to every install call and by disabling the
   default internet sources for the duration of the install, so any future gap
   fails loudly instead of silently succeeding via a fallback that won't exist
   in production.
4. **Obsidian's t64 naming mismatch** — Obsidian's upstream `.deb` declares
   `Depends: libgtk-3-0, libatspi2.0-0` (pre-Debian-t64-transition names) which
   no longer exist in Debian 13 trixie (renamed to `libgtk-3-0t64` /
   `libatspi2.0-0t64`). Fixed by building two small compatibility shim packages
   (`libgtk-3-0`, `libatspi2.0-0`, epoch `999:1`) that simply Depend on the
   real t64 packages, included in the curated repository.

## Final Status

```
PASSED
```

This release is approved for publication.
