# RAH Infrastructure Golden Baseline

This document is a pointer/reference. It identifies an external validation
asset — a Hyper-V VM checkpoint — that is not, and cannot be, stored in this
Git repository. The checkpoint itself lives only on the Legion (Windows 11
Hyper-V host) that hosts the lab VMs.

---

## Snapshot

```
GoldenSnapshot-WithRAHOIP
```

Created: **2026-07-16 11:03:29**

## VM

```
Offline-AirGapped-Simulator
```

## Target OS

Debian 13 (trixie), amd64

## Purpose

Preferred baseline for Application Release and Platform validation testing.
Using this snapshot instead of a clean Debian install skips re-running the
~10-minute RAH-OIP infrastructure installation on every test cycle.

## State Captured

Everything in the pre-Docker baseline (see below), plus RAH-OIP-1.0.0 fully
installed and verified:

- Docker Engine + Docker Compose plugin
- Curated local APT repository (offline package source)
- Portainer CE
- SQL Server and PostgreSQL images loaded
- DBeaver
- Obsidian
- xrdp
- CLI utilities (git, curl, wget, htop, nano, vim, rsync, zip, unzip, tmux, tree)

## Corresponding Infrastructure Release

```
RAH-OIP-1.0.0_Debian13_2026-07-09
```

This release's engineering content (scripts, manifest, checksums, validation
report) is tracked directly in this repository under `infrastructure/` — see
`infrastructure/README.md`. Its multi-GB binaries (Docker image `.tar`
exports, the curated `.deb` package pool) are gitignored but present on disk
alongside the tracked content for local build/test use.

The original source of this material, `RAH-Offline-Platform-Export` on the
Legion's Desktop (its own separate local git repository), still exists as
historical raw material but is no longer the canonical copy — this
repository is.

---

## Predecessor Snapshot

```
GoldenSnapshot-WithNetwork
```

Created: **2026-07-09 11:27:29**

Pre-Docker baseline. Contains: clean Debian 13 desktop, no Docker, no prior
release artifacts, static IP `10.10.10.2/24` persistently configured, no
internet access. `GoldenSnapshot-WithRAHOIP` was taken from this baseline
after installing and verifying RAH-OIP 1.0.0 on top of it.

## Do Not Use

The Hyper-V auto-generated checkpoint (`Automatic Checkpoint -
Offline-AirGapped-Simulator - (7/9/2026 - 8:59:22 AM)`) predates the network
configuration. Reverting to it leaves the VM with no working network and
requires manual reconfiguration through the Hyper-V console.

---

## Important

**The Hyper-V snapshot itself is external to Git.** It is a saved VM disk +
memory state (VHDX differencing disks and Hyper-V XML/VMCX metadata) managed
by Hyper-V on the Legion host — not a file or folder that can be committed,
cloned, or version-controlled the way source code can. This document is only
the canonical pointer: what it's called, what it contains, and what it
corresponds to. Full connection details, credentials, and revert/checkpoint
commands live in the local-only (non-Git) lab reference — see
`lab-environment-sanitized.md` in this directory for the non-secret subset of
that information.
