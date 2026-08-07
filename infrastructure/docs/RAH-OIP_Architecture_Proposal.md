# RAH Offline Infrastructure Platform — Engineering Proposal

Written mid-project, after the DVD kit had already hit two real validation failures
(missing `libfuse2t64` dependency for xrdp, Docker assumed pre-installed rather than
included) and the `opensysusers`/`systemd-standalone-sysusers` conflict caused by
hand-computed dependency closures. This was the point where the "kit" stopped being a
folder of scripts and started needing to be treated as a proper release-engineering
product. Reconstructed from chat — this never existed as a standalone file until now.

---

## Part 1 — What this should actually become

Reframe: this is no longer a "kit" (a bundle of files someone assembles once) but a
**versioned, reproducible software distribution for air-gapped deployment** — the same
category of thing as a Linux vendor's install media, or how Rancher/OpenShift ship
"disconnected" bundles for air-gapped Kubernetes.

**The actual problem being solved:** every failure hit up to this point traced back to one
root cause — *we were manually reconstructing what a real package manager does, by hand,
per-component, per-kit-build.* That doesn't scale and re-breaks every time. The
platform's real job is to remove that manual step entirely.

**Proposed name:** RAH Offline Infrastructure Platform, short form RAH-OIP. Version-stamped
like a product, e.g. `RAH-OIP 1.0.0 for Debian 13`.

## Part 2 — Versioning

Semantic versioning, adapted:

| Segment | Bumped when |
|---|---|
| MAJOR | Target OS version changes, or a breaking architecture change |
| MINOR | New component added, or a component's major version bumped |
| PATCH | Security fixes, dependency-closure corrections, doc fixes |

Every release carries a full identity: release version, target OS + point-in-time
snapshot, publication date, and a full component version table (Docker, Compose,
Portainer, SQL Server, Postgres, DBeaver, xrdp, etc.) with exact digests/tags.

**Release management rule, non-negotiable:** once published, a release is immutable.
No hotfixing a release in place — cut a new PATCH instead. Every published release is
retained forever in an archive alongside its manifest and validation report.

## Part 3 — Should Debian updates be in scope? Full Releases vs. Update Packs

Yes, unambiguously. The single most important architectural change: **stop hand-picking
`.deb` files via `apt-cache depends --recurse`.** That approach is exactly what produced
the `opensysusers`/`systemd-standalone-sysusers` conflict — it's a graph-traversal
heuristic, not a real solver.

Instead: build a **frozen local APT repository snapshot** — a real repo with
`Packages`/`Release` metadata (via `apt-mirror`, `debmirror`, or `aptly`/`reprepro`).
Ship that as the platform's OS layer. On the offline target, point `apt` itself at this
local repo and let **the real apt solver** — the one Debian itself trusts — do dependency
resolution, using the target's actual installed-package state.

Two tiers: **Platform Mirror** (filtered snapshot of exactly the declared component set's
transitive closure) as the primary shipped artifact, and an optional **Full OS Mirror**
(complete Debian main+security) for hospitals wanting general package availability.

**Full Releases** (`X.Y.0`): complete platform, new-install use case.
**Update Packs** (`X.Y.Z`): delta only, patching-an-existing-install use case.

## Part 4 — Redesigned project structure

Separate three concerns that a flat numbered-folder kit conflates: how **we** build a
release, what actually **ships** in the box, and the **governance metadata** around a
release.

```
rah-oip/
├── releases/
│   ├── 1.0.0/
│   │   ├── MANIFEST.yaml
│   │   ├── RELEASE_NOTES.md
│   │   ├── COMPATIBILITY_MATRIX.md (+.yaml)
│   │   ├── VALIDATION_REPORT.md
│   │   └── kit/                     <- what goes on the USB/DVD
│   │       ├── 01_platform_mirror/  (frozen local APT repo)
│   │       ├── 02_platform_validation/
│   │       ├── 03_container_runtime/
│   │       ├── 04_container_images/
│   │       ├── 05_database_tools/
│   │       ├── 06_productivity_tools/
│   │       ├── 07_remote_access/
│   │       ├── 08_cli_utilities/
│   │       ├── 09_install_orchestration/  (declarative install manifest)
│   │       ├── 10_verification/
│   │       ├── 11_documentation/
│   │       └── CHECKSUMS.txt
│   └── ...
├── build/        (release engineering tooling — NOT shipped)
├── validation/   (clean-VM snapshot definitions, test scripts, report archive)
└── docs/         (living master docs, templates frozen into each release)
```

Key changes from a flat numbered structure: OS content (mirror) split from OS
verification; Docker install/verify unified into the single central verification stage;
generic naming ("Container Runtime" not "Docker Kit") so it survives a future runtime
change; and a new `09_install_orchestration/` — a declarative manifest an orchestrator
reads, so "run things in the right order together" isn't left to operator memory (this
directly targets the failure mode where someone ran `dpkg -i` on one file instead of a
whole folder).

## Part 5 — Guaranteeing compatibility

A formal Compatibility Matrix, both human-readable and machine-readable (YAML), generated
per release — not hand-maintained. Compatibility guaranteed by **process**: every
component pinned by exact tag/digest; the Platform Mirror is one atomic point-in-time
snapshot (guarantees internal consistency by construction, unlike per-package
`apt-get download` runs which can silently mix versions across days); a release only
publishes after passing the Validation Pipeline; cross-component claims recorded from
actual tested runs, not vendor docs.

## Part 6 — Validation pipeline

| Stage | What happens |
|---|---|
| 0. Golden Base Snapshot | Version-controlled clean-VM baseline |
| 1. Build | Assemble the release on the online engineering VM |
| 2. Static verification | Manifest completeness + local-repo dependency-closure simulation across the *entire* platform, as a mandatory automated gate |
| 3. Dynamic verification | Restore Golden Snapshot, sever network access, copy candidate release, run install end-to-end |
| 4. Acceptance tests | Beyond "service is running" — actually create a test DB, actually start each container, actually attempt an xrdp connection |
| 5. Report & sign-off | Auto-generate `VALIDATION_REPORT.md`, named human sign-off required |
| 6. Publish & archive | Only after sign-off does a release move from candidate to published; archived forever |

## Part 7 — Long-term evolution

Full Releases every 3–6 months (not monthly — validation overhead disproportionate to
actual pace of change in a stable hospital environment). Update Packs as needed for
security/corrections. Security Update Packs fast-tracked but still always gated and
logged. MAJOR versions reserved for target-OS bumps, always full lifecycle. An N-1
deprecation policy so hospital IT has a predictable upgrade horizon. Archive everything
forever. Name a release owner, even a rotation of one person, for accountability over a
multi-year horizon.

## Part 8 — Documentation proposal

Two tiers: **living/master** docs (`ARCHITECTURE.md`, `VERSIONING_POLICY.md`,
`DOCUMENTATION_INDEX.md` — one canonical copy, updated as the platform evolves) vs.
**per-release frozen** docs (`RELEASE_NOTES.md`, `COMPATIBILITY_MATRIX.md`,
`VALIDATION_REPORT.md`, append-only `CHANGELOG.md`, `KNOWN_ISSUES.md`,
`INSTALLATION_MANUAL.md`, new `UPDATE_MANUAL.md`, new `RECOVERY_MANUAL.md`,
`OPERATOR_MANUAL.md`, `VERSION_HISTORY.md` — finalized at publish time, immutable after).

---

**Where this pushed hardest against the existing trajectory:** the recurring failure
mode across every round of testing had been *us* acting as the dependency solver by hand,
discovered reactively on a validation VM after the fact each time. The mirror-snapshot
approach in Part 3 is the one change that converts this from "we keep finding gaps after
they break something" into "the real solver catches it before we ever ship." Everything
else here is organizational discipline; that one is the actual engineering fix.
