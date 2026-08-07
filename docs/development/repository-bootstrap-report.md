# Repository Bootstrap Report

How this repository (`Air-Gapped-System-Platform`, the canonical RAH Release
System project) was assembled from prior work spread across an Obsidian
vault and a separate Desktop export folder. Written for future Claude
sessions who need to know where the content came from and why it's shaped
the way it is — not a changelog, a provenance record.

## What existed before this repository was populated

- **Architecture and development planning** — Markdown files in an Obsidian
  vault (`OneDrive\Obsidian\...\Stages Of Design & Though` and
  `...\Stages Of Deployment`), the product of Stages 1-7 architecture design
  and Period A/B/C development planning, done in prior sessions.
- **Infrastructure engineering** — `RAH-Offline-Platform-Export` on the
  Legion's Desktop: the RAH-OIP (Infrastructure Release) scripts, docs,
  manifest, and validated Docker/APT assets, built and tested independently
  of the architecture-planning work above, with its own local git history
  (`git init` done in a prior session, commit `7086fa2`).
- **A second, mistakenly-created repository** —
  `C:\Users\it\Documents\GitHub\rah-release-system` — created by literally
  following a GPT-authored bootstrap mission prompt without cross-checking
  it against this repository, which already existed and already had a
  GitHub remote. Caught by the user, consolidated into this repository, then
  deleted. No trace of it remains.

## What got migrated here, and how

1. `docs/architecture/` — the 12 Stage documents copied verbatim from the
   Obsidian "Stages Of Design & Though" folder, verified byte-identical via
   `Compare-Object`. Includes the applied Operation Identity Model gap fix
   (an `operations` table added as the unified deployment/verification/
   backup identity record, done in the Obsidian originals before copying).
2. `docs/development/` — the planning documents from Obsidian's "Stages Of
   Deployment" folder (development strategy/rules, GitHub-based-memory
   theory, development plan overview, per-period plans for Packager A,
   Platform A, Period B, Period C), plus `CURRENT.md`, written fresh as the
   live status file this repository didn't have an equivalent for.
3. `docs/infrastructure-reference/` — written fresh: sanitized pointers to
   the Hyper-V Golden Snapshot baseline and the lab environment, deliberately
   excluding real credentials (SSH key paths, VM passwords) that exist only
   in the Desktop export's `RAH-OIP_LAB_ENVIRONMENT_REFERENCE.md`.
4. `docs/decisions/` — standalone explainers written on request (e.g.
   `why-curated-apt-repository.md`), for questions worth answering once and
   keeping around rather than re-explaining every session.
5. `infrastructure/` — the full RAH-OIP Infrastructure Release, duplicated
   into this repository rather than merely referenced. This was an explicit
   user decision, overriding an earlier "don't duplicate infrastructure"
   assumption:

   > "This directory is where the system must live, and that part must be
   > integrated one way or another into this system... I want duplication."

   The reasoning given: this platform is installable software, and
   everything needed to build a ~4GB release image must come from this one
   repository — no external folder dependency at build time. All 99
   git-tracked files from the Desktop export's repository were copied
   preserving their original relative structure
   (`offline-debian-server-kit/`, `rah-oip-releases/...`, `docs/`,
   `lessons-learned/`). The three Docker image `.tar` exports
   (postgres, mssql, portainer) were copied in physically, gitignored.

## The APT pool colon-filename problem (cross-session collaboration)

A second Claude session, running on the lab's Online Debian VM ("OR-STT",
has internet access), independently diagnosed and fixed a Windows-specific
problem: 58 of 312 real Debian package filenames contain a literal `:`
(the epoch version prefix, e.g. `docker-ce-cli_5:29.6.1-...`), which Windows
NTFS cannot represent. Loose-file copies of the pool silently produced
0-byte stub files for exactly those 58 packages when brought onto this
Windows machine — confirmed independently on both sides.

The fix (implemented by the online-VM session, verified present and correct
by this session): archive the entire pool as one opaque `pool.tar.gz` file
instead of loose files. Tar/zip formats don't care what characters appear in
an internal entry name; only the OS does when something tries to extract it
raw. The archive is committed; it gets extracted only on a Linux machine, at
the point it's actually needed.

This is documented in three places, intentionally kept in sync:
- `infrastructure/EXPLANATION_FOR_LENOVO_CLAUDE_pool_colons.md` — the
  original diagnosis and the three options considered.
- `infrastructure/COMPLETE_BRIEFING_FOR_LENOVO_CLAUDE.md` §4 — the current
  consolidated status.
- `infrastructure/.../01_APT_Repository/README.md` — the practical
  extract-it-here instructions, next to the archive itself.

**Open, not yet decided:** whether the archive-blob approach is the
permanent answer, or whether the pool should become a generated build
artifact instead (not committed to git at all, regenerated fresh from a
package list on a Linux build machine each release — closer to how
`node_modules` isn't committed). The online-VM session explicitly flagged
this as a structural decision for the user to make, not something either
Claude session should just pick. Still open.

## Application validation lessons

The same online-VM session ran four real hospital application releases
(HCopilot, STT-SCHEDULE, Voice Project, Indicator) through install/verify
cycles on the offline air-gapped simulator VM and found real, since-fixed
bugs. Distilled into `docs/development/application-validation-lessons.md`
because the recurring patterns (host-mount UID ownership, placeholder
secrets failing late, hardcoded ports/URLs, offline-invisible internet
dependencies) are direct constraints on the Release Contract and Packager
design, not just historical trivia.

## Known residual gaps

- `infrastructure/docs/RAH-OIP_LAB_ENVIRONMENT_REFERENCE.md` (real
  credentials) is correctly excluded from this repository by `.gitignore`
  (`**/*LAB_ENVIRONMENT_REFERENCE*`). It exists only in the Desktop export
  and should never be committed anywhere.
- Cross-session synchronization: the online-VM Claude session's
  understanding of this project's progress can lag behind this repository's
  actual state, since it works from handoff documents rather than this git
  history directly. Treat its handoff docs as a snapshot in time, not a live
  feed.
