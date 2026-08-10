# Current Development State

## Current Phase

Period A, Packager track. Release Contract V1 is **FROZEN** (user-confirmed).
Packager `P0` done; `P1` is the active next slice.

## Architecture

Architecture V1: READY FOR EXECUTABLE CONTRACT MATERIALIZATION.

Frozen theoretical image lives in `docs/architecture/`. Not to be reopened
casually — changes should come from implementation evidence, not
speculative redesign.

## Period A — Packager

Status: **P0 DONE** (runtime/CLI foundation — `packager/`, 14/14 tests
pass, all required proofs verified live against the real container).
**P1 (Project Initialization) is next** — unblocked, Contract V1 is frozen.
See `docs/development/Period A — Independent Product Development;
Packager/2. Initial Slicing Task Table.md`.

## Period A — Platform

Status: NOT STARTED

## Period B — Integration

Status: NOT STARTED

## Period C — Jenkins

Status: NOT STARTED

## Current Mission

1. Bootstrap canonical Git repository — **DONE** (this repository).
2. Migrate architecture and development documentation — **DONE**.
3. Materialize Release Contract V1 in `contracts/1.0/` — **DONE**. All four
   files written and tested (`release-layout.yaml`,
   `release-manifest.schema.json`, `validation-rules.json`,
   `compliance-report.schema.json`), plus `contracts/1.0/README.md`.
4. Review Contract completion decisions (EXTRACTED / COMPLETED /
   ARCHITECTURE CONFLICT) — **DONE**. Zero ARCHITECTURE CONFLICT items
   found. See `docs/development/contract-v1-completion-log.md`.
5. Freeze Executable Contract V1 — **DONE**. User-confirmed: *"I accepted
   the release Contract V1. It is good. We will build on it."* Any edit is
   explicitly deferred by the user to later, not reopened speculatively.
6. Begin Period A development (Packager and Platform, independently) —
   **IN PROGRESS**. Packager `P0` done and tested; `P1` (Project
   Initialization, `rah init`) is next. Platform track not started. See
   `docs/development/Period A — Independent Product Development;
   Packager/2. Initial Slicing Task Table.md`.

## Candidate Applications for Packager/Platform Acceptance Testing

Five real hospital applications exist as candidates for the "choose the real
application" decision (Current Mission step 5 onward). They are distinct,
unrelated applications despite two of the names looking similar:

- **HCAT** — backend `C:\Users\it\Documents\GitHub\Patient_Feedback`,
  frontend `C:\Users\it\Documents\GitHub\Front_End_Feedback_Analysis`. Not
  yet run through the offline validation pipeline.
- **HCopilot** — `C:\Users\it\Documents\HCopilot\HCopilot`. A **different,
  unrelated** application from HCAT — SQL Server-backed. Already validated;
  see `docs/development/application-validation-lessons.md`.
- **STT-SCHEDULE** — `C:\Users\it\Documents\GitHub\STT-SCHEDULE`. Postgres +
  pgAdmin. Already validated.
- **Voice Project (Blood Bank)** —
  `C:\Users\it\Documents\GitHub\voice-project_Deployment`. SQL Server +
  Whisper speech-to-text. Already validated.
- **Indicator (Healthcare Reporting)** —
  `C:\Users\it\Documents\GitHub\Healthcare_reporting_system_backup`. No
  database, simplest of the five. Already validated.

The four already-validated applications carry real, confirmed bugs and fixes
from offline-simulator testing — see
`docs/development/application-validation-lessons.md` for what broke and why
it matters for the Release Contract and Packager design specifically
(placeholder-password handling, host-mount UID ownership, port
reconfigurability, offline-only runtime behavior).

### Acceptance decision (settled)

**HCopilot is the Period A Packager P0 acceptance app.** **Indicator is the
required second acceptance app** — not an optional stretch goal — because
the Packaging Engine's polymorphism claim (heterogeneous source projects
→ identical Release shape, via the `ProjectInspectionResult` →
`EngineeringRequestResult` hybrid discovery/ask-gap mechanism in
`docs/architecture/4.6. Stage 4 — Packaging Engine Specification.md`) has
only ever been *designed*, never *proven*. One app run through the
Packager proves the pipeline runs; it doesn't prove the mechanism
generalizes. HCopilot (SQL Server-backed) and Indicator (no database at
all) are structurally different enough to be a real first test.
STT-SCHEDULE and Voice Project follow after this pair.

**HCAT is deliberately deferred**, not because it isn't a candidate, but
because it introduces a distinct problem the Contract needed to resolve
first: multiple bundled ML models. **Resolved during Contract
materialization**: no separate `assets`/`models` directory exists in
`release-layout.yaml` — all app-specific binary content, ML models
included, bakes into a Docker image via ordinary `COPY`, checked against
real evidence that the previous "separate asset" approach (Voice Project's
Whisper model) was already re-shipping an unchanged, byte-identical file
in every release version with zero deduplication benefit. See
`docs/decisions/packager-responsibility-boundaries.md` and completion-log
item 1/2 in `docs/development/contract-v1-completion-log.md`. `RC-OFF-004`
in `validation-rules.json` covers the hardcoded-runtime-download check
this paragraph originally asked for.

## Current Blocking Dependency

None for Packager `P1`. Release Contract V1 is frozen.

## Next Major Gate

Packager `P1` (Project Initialization — `rah init`) complete and tested.

## Future Design Tasks (not yet started)

- **Packager operational error-code namespace** (e.g. `PKG-*`, distinct
  from the Contract's `RC-*` validation-rule namespace) — covering Git
  inspection, Docker discovery, Claude interaction, configuration, and
  runtime failures. Real gap, deliberately not designed yet — needs its
  own small architectural discussion before Packager `P0`/`P5`
  implementation needs it. See
  `docs/development/Period A — Independent Product Development;
  Packager/1. Initial GPT Proposal.md` (P5, where `PKG-DOCKER-*` is
  referenced as if it already exists).

## Related References

- `docs/development/repository-bootstrap-report.md` — how this repository was assembled.
- `docs/infrastructure-reference/golden-baseline.md` — the RAH Infrastructure
  Golden Baseline (Hyper-V snapshot `GoldenSnapshot-WithRAHOIP`), the
  preferred Platform testing baseline.
- `docs/development/1. Development Strategy and Engineering Rules.md` — the
  17 governing development rules (not yet renamed to `00-development-rules.md`;
  content was preserved as-is during migration, see bootstrap report).
- `docs/decisions/packager-responsibility-boundaries.md` — who actually does
  what between Docker, Claude (at app-dev time vs. packaging time), and the
  Packager's own deterministic code; the "everything bakes into Docker
  images" decision; confirmation that Release versions are additive, never
  overwritten.
- `docs/development/contract-v1-completion-log.md` — the review artifact
  for freezing Release Contract V1: every COMPLETED decision, cited
  architecture source, and a cross-check against HCAT's/Voice Project's
  real (pre-Contract) release folders.
