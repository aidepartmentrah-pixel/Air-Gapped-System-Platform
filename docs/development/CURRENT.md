# Current Development State

## Current Phase

Period A, Packager track. Release Contract V1 is **FROZEN** (user-confirmed).
Packager `P0`, `P1`, `P2`, and `P3` are all done — `P3` (Claude Knowledge
Bridge) finished with `rah prepare-answers` built, tested, and live-proven
against the real Anthropic API. `P4` (Release Planning) is next.

## Architecture

Architecture V1: READY FOR EXECUTABLE CONTRACT MATERIALIZATION.

Frozen theoretical image lives in `docs/architecture/`. Not to be reopened
casually — changes should come from implementation evidence, not
speculative redesign.

## Period A — Packager

Status: **P0 DONE** (runtime/CLI foundation — `packager/`, 14/14 tests
pass, all required proofs verified live against the real container).
**P1 DONE** (`rah init` / Project Version State — 12 new tests, 26/26
total pass, all required proofs verified live against the real built
container, including a real run against a clone of HCopilot).
**P2 DONE** (`rah inspect` — all 4 categories: Git, Docker, Application
Resources, Packager State — 26 new tests, 52/52 total pass, verified live
against a real HCopilot clone **and** the real Indicator repo directly,
proving the `ProjectInspectionResult` shape generalizes across two
structurally different apps with zero per-app branching).
**P3 DONE** (Claude Knowledge Bridge). The design gap the architecture
left open — no pre-drafted `engineering-answers.schema.json` or staleness
mechanism, unlike P1/P2 — is closed:
`docs/decisions/engineering-answers-and-staleness.md` written, schema
derived field-by-field from the real frozen Release Manifest schema,
`rah validate-answers` (schema + cross-consistency + two-anchor staleness
check) and `rah prepare-answers` (real Claude API call, forced tool-use,
three-tier suggestion pre-fill, unconditional-overwrite re-run behavior)
both built and live-proven against a real repo with real Anthropic API
spend — including a real new commit correctly detected as staleness after
a real Claude-generated answer. 56 new tests across this slice (52 → 108
total), 108/108 pass. Also built as a prerequisite: real Claude API credential handling
(`Config.anthropic_api_key`, `rah health` reporting it, live-proven
against the real Anthropic API with the engineer's real key). See
`docs/development/Period A — Independent Product Development;
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
   **IN PROGRESS**. Packager `P0`, `P1` (Project Initialization,
   `rah init`), `P2` (Repository Inspection, `rah inspect`), and `P3`
   (Claude Knowledge Bridge, `rah prepare-answers` + `rah validate-answers`)
   all done and tested. `P4` (Release Planning) is next. Platform track
   not started. See
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

None. Packager `P0`–`P3` are all done. `P4` (Release Planning) has no
open design gap — see the Master Development Matrix in the Slicing Task
Table for its dependencies.

## Next Major Gate

Packager `P4` (Release Planning) — the next slice in the matrix, building
on the now-complete `P1`–`P3` foundation (Project Version State,
`ProjectInspectionResult`, and Engineering Answers).

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

- `docs/development/SESSION_START.md` — read automatically every session
  via the repo-root `CLAUDE.md`. Phase-agnostic bootstrap: what to read,
  how the docs are organized, working discipline. Don't add project status
  there — it belongs here in `CURRENT.md`.
- `docs/development/repository-bootstrap-report.md` — how this repository was assembled.
- `docs/infrastructure-reference/golden-baseline.md` — the RAH Infrastructure
  Golden Baseline (Hyper-V snapshot `GoldenSnapshot-WithRAHOIP`), the
  preferred Platform testing baseline.
- `docs/development/1. Development Strategy and Engineering Rules.md` — the
  17 governing development rules (not yet renamed to `00-development-rules.md`;
  content was preserved as-is during migration, see bootstrap report).
- `docs/decisions/engineering-answers-and-staleness.md` — the P3 design the
  frozen architecture left open: `engineering-answers.schema.json` derived
  field-by-field from the real Release Manifest schema, and the two-anchor
  (Git commit + inspection fingerprint) staleness mechanism.
- `docs/decisions/packager-responsibility-boundaries.md` — who actually does
  what between Docker, Claude (at app-dev time vs. packaging time), and the
  Packager's own deterministic code; the "everything bakes into Docker
  images" decision; confirmation that Release versions are additive, never
  overwritten.
- `docs/development/contract-v1-completion-log.md` — the review artifact
  for freezing Release Contract V1: every COMPLETED decision, cited
  architecture source, and a cross-check against HCAT's/Voice Project's
  real (pre-Contract) release folders.
