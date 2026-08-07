# Air-Gapped System Platform (RAH Release System)

The source repository for the RAH Release System: the Packaging Engine, the
Offline Installation Platform, their shared Application Release Contract,
integration testing, and Jenkins qualification automation — plus the
architecture and development memory that governs how they're built.

This repository is the **canonical project memory**: architecture, living
development plans, current development state, and testing evidence live
here as Markdown alongside the eventual source code, not in a separate
Obsidian-only copy that can drift out of sync. Obsidian may still be used to
*view and edit* these same files (open `docs/` as a vault), but this
repository is the one editable copy.

## What this repository is not

- **Not a separately maintained project.** The RAH-OIP Infrastructure
  Release — curated APT repo, Docker/Compose install scripts, infrastructure
  Docker images (Portainer, SQL Server, PostgreSQL base images) — is an
  already-built, already-validated, independently versioned asset
  (`RAH-OIP-1.0.0`) with its own release history. But because this platform
  is installable software and everything it needs to build a release must
  come from this one repository, its engineering content (scripts, manifest,
  checksums, docs) is deliberately duplicated here under `infrastructure/`,
  not merely referenced. Its large binary payload (Docker image `.tar`
  exports, the curated `.deb` package pool) is gitignored but present on
  disk for local build/test — see `infrastructure/README.md` and
  `docs/infrastructure-reference/` for the full explanation and what stays
  external (the Hyper-V snapshot, lab credentials).
- **Not** the Hyper-V Golden Snapshot. That's a VM checkpoint on the lab
  host, not something Git can hold — see
  `docs/infrastructure-reference/golden-baseline.md` for what it is and how
  it relates to this project.
- **Not** a Docker-management replacement like Portainer, and not a second,
  competing definition of what a Release is — the Application Release
  Contract in `contracts/` is the single source of truth for that; the
  Packager produces Releases against it, the Platform consumes them through
  it.

## Repository layout

```
contracts/1.0/          Machine-readable Application Release Contract
                         (release-manifest.schema.json, release-layout.yaml,
                         validation-rules.json, compliance-report.schema.json)
                         — not yet materialized, next mission.

packager/                RAH Packaging Engine source (not yet started).
platform/                RAH Offline Installation Platform source (not yet started).
integration-tests/       Cross-product (Packager -> Platform) integration tests.
jenkins/                 Jenkins qualification pipeline (Period C, later).
tests/                   Shared/top-level test resources.

infrastructure/          RAH-OIP Infrastructure Release (Docker, curated APT
                         repo, install/verify scripts) duplicated in full —
                         engineering content tracked, large binaries
                         gitignored but present on disk. See its own
                         README.md.

docs/
  architecture/           The frozen theoretical image of the system —
                           Stages 1-7, the Release Contract, Packaging Engine
                           and Platform specifications. Mostly read-only;
                           changes here should come from implementation
                           evidence, not speculative redesign.
  development/            Living development memory — development rules,
                           the three-period build program (A/B/C), per-period
                           plans, slices, and current status. This is the
                           part Claude and future sessions update constantly.
  infrastructure-reference/ Sanitized, non-secret pointers to the external
                           RAH-OIP infrastructure release and the Hyper-V
                           Golden Snapshot baseline.
  decisions/              Standalone architecture decision records.
```

## Current state

**Pre-development.** Architecture is substantially defined (Architecture V1).
The next technical mission is materializing the four executable Release
Contract files in `contracts/1.0/` from the frozen prose architecture. See
`docs/development/CURRENT.md` for the live status.

Implementation (Packager, Platform, Jenkins) has not started yet. Period A
(independent Packager and Platform development) begins after the Contract is
materialized and reviewed.
