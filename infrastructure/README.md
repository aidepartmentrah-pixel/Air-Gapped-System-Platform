# RAH Offline Platform — Export from the Lab VM

Everything from the online lab VM relevant to starting the RAH Offline Installation
Platform project on GitHub: the existing DVD kit, the newer RAH-OIP structured release,
and every lesson learned building and validating both. Exported 2026-08-06.

**Nothing here has been organized into a "correct" repo shape on purpose** — that
decision is yours to make once you can actually see everything laid out. This is raw
material, not a proposal for final structure.

## What's in here

### `offline-debian-server-kit/`
The original flat-structure DVD kit (00_START_HERE.md → 10_remote_desktop/). This is
what's actually been tested and used for real installs so far — Docker, Portainer,
SQL Server/Postgres images, DBeaver (+ the JDBC driver auto-population fix), Obsidian,
xrdp, CLI utilities. ~1.2 GB, mostly Docker image tars and `.deb` packages — **not
git-friendly as-is**. If this becomes the seed of a real git repo, the large binaries
(image tars, `.deb`/`.jar` files) almost certainly want to be either gitignored and
fetched/built at release time, or tracked with Git LFS — committing them directly will
make the repo unpleasant to clone/work with fast.

### `rah-oip-releases/`
The newer, versioned release structure (`RAH-OIP-1.0.0_Debian13_2026-07-09/`) — curated
local APT repository (real `Packages`/`Release` metadata, not hand-picked `.deb`s),
`MANIFEST.yaml`, `COMPATIBILITY_MATRIX.md`, `VALIDATION_REPORT.md`, `RELEASE_NOTES.md`.
This is the more disciplined shape from the architecture proposal in `docs/`, but it's
only ever been built once — the kit above is what's actually been through repeated real
validation and bug-fixing. ~2.5 GB, same binary-size caveat as above.

### `docs/`
- `RAH-OIP_Architecture_Proposal.md` — the full 8-part release-engineering proposal
  (versioning, release structure, validation pipeline, long-term evolution, documentation
  set) written partway through this project, after the kit had already hit real
  dependency-closure failures. Reconstructed from chat history — this is the reasoning
  behind why `rah-oip-releases/` looks the way it does.
- `RAH-OIP_LAB_ENVIRONMENT_REFERENCE.md` — machine inventory, credentials, connection
  methods, and gotchas for the two-VM lab setup (online VM + air-gapped simulator VM,
  both hosted on this Legion via Hyper-V) this was all built and tested against.

### `lessons-learned/`
Everything Claude's cross-session memory accumulated while working on this — real bugs
found during validation and their root causes, not hypotheticals:
- `rah_oip_lab_topology.md` — why the two-VM (online + air-gapped simulator) setup exists
- `rah_oip_environment_reference_file.md` — pointer/summary version of the environment doc
- `voice_project_release_validation.md` — Whisper-needs-internet bug, database
  verification path/permission bugs, nginx WebSocket bug, CDN-dependency bug — all found
  and fixed on the Blood Bank (Voice) project's release package
- `stt_schedule_release_validation.md` — pgAdmin UID-permission crash-loop bug, `@` in a
  password breaking a `DATABASE_URL`, Postgres port exposure for DBeaver
- `MEMORY.md` — index of the above

## The recurring bug pattern worth knowing before you start

Three separate times, across three different applications, the same root cause: **a
Docker container running as a fixed non-root UID couldn't read/write a host-mounted
directory that was created owner-only (usually because a root-run install script created
it via `sudo` without fixing ownership afterward).** pgAdmin (UID 5050), the SQL Server
container reading mounted validation scripts (UID 10001), and DBeaver's driver cache all
hit variants of this. Worth designing around explicitly in whatever the platform becomes
— e.g. always `chown`/`chmod o+rX` anything a script creates as root but a non-root
container needs to read.

## Suggested next step (not a directive)

Read `docs/RAH-OIP_Architecture_Proposal.md` first — it's the most complete articulation
of where this was heading before the scope expanded into the UI-platform idea. Then
decide whether the platform project wraps around `rah-oip-releases/`'s release shape
(recommended, since it's the one with an actual compatibility matrix and validation
report format already defined) or something new entirely.
