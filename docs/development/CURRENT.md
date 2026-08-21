# Current Development State

**As of 2026-08-21**: Period A (both tracks, Packager and Platform) is
fully closed — see "Current Mission" step 6 below for the complete exit-
gate evidence. **Period B has started**: `B0`, `B1`, `B2` are DONE, an
urgent interstitial fix (`B2+`) is also DONE, `B3` (retry) is next —
see "Period B — Integration" below. The rest of this "Current Phase"
section is preserved as Period A's own detailed historical record and is
no longer the live status; skip to "Period B — Integration" for what's
actually current.

## Current Phase

Period A has two independent tracks. Release Contract V1 remains
**FROZEN** (user-confirmed).

Packager `P0`–`P7` are automated-portion-done. **The Real Manual
Acceptance Test has been executed** (2026-08-11, real Indicator app, real
lab hardware) and **FAILED at Phase 1**: `rah package` correctly rejected
the candidate at `RC-SCR-005` — Indicator's own lifecycle scripts were
committed to Git without the executable bit, a real gap in the Indicator
repo, not the Packager. Full results:
`docs/development/Period A — Independent Product Development;
Packager/3. Real Manual Acceptance Test — Results.md`.

**`RC-SCR-005` is now fixed** (18/08/2026, on this Windows engineering
workstation, committed and pushed to Indicator's `master`) — see "Open
Items" below for this and four other real fixes done the same day.

**Phase 1 re-run, confirmed for real, 19/08/2026**: `rah package` against
a fresh disposable clone of Indicator (`master`, `RC-SCR-005` fix in
place) → `overall_result: PASS`, real finalized `Indicator_Release_1.0.0`
(46 rules PASS, 6 correctly `NOT_APPLICABLE` — no database, matching
Indicator's own shape — 0 FAIL), both images built and archived. This is
the first time Phase 1 has ever passed for Indicator. Two things were
needed to get there, both real and worth carrying forward:
- Bind-mounting Indicator's live Windows working directory directly hit
  the CRLF/git-dirty gap from the original P7 proof (`core.autocrlf=true`
  set only in the host's *global* gitconfig, invisible to the container,
  so nearly the entire tree read as "modified" from inside it). Worked
  around the same way as before: a disposable clone, then
  `git config core.autocrlf input && git checkout -- .` from inside the
  container.
- A real gap in Claude's freshly generated engineering answers:
  `configuration.inputs` was populated but `configuration.template` was
  left out entirely, even though P2's own inspection had already found a
  matching candidate (`release/compose/.env.offline.template`, whose 5
  keys line up exactly with the 5 declared inputs) — `rah package`
  correctly refused with `PKG-MANIFEST-INCOMPLETE` rather than silently
  proceeding. Corrected by hand once identified.

**Phases 2–6 executed for real, 20/08/2026 — ALL PASSED.** This is the
first time the full Real Manual Acceptance Test has ever passed end to
end, for any RAH application, through this Packager. Lab access was
resolved this session: the Legion hosts both `OR-STT` and
`Offline-AirGapped-Simulator` via Hyper-V (confirmed `Offline-Lab` is a
**Private** switch, so `OR-STT` is the only possible hop to the offline
VM — no host-level path exists); a fresh SSH keypair was added to
`OR-STT` directly via the Hyper-V console (its real login is
`orstt`/`123`, not `root` — this doc previously never recorded it at
all); `Offline-AirGapped-Simulator` was reverted to
`GoldenSnapshot-WithRAHOIP` (not `GoldenSnapshot-WithNetwork`, which is
now the superseded pre-RAH-OIP baseline) and confirmed genuinely
air-gapped (`curl` to a public IP failed outright).

- **Phase 2 (Transfer)**: PASS. Release + Packager image copied
  Legion → `OR-STT` → offline VM over the internal switch only.
- **Phase 3 (Independent re-validate)**: PASS, zero checksum mismatches,
  proving the bytes survived the full transfer bit-for-bit with zero
  network dependency on the validating side — the one proof no automated
  test suite could ever provide on its own.
- **Phase 4 (Install)**: PASS, but only after **three real, previously-
  unknown bugs** were found and fixed live — see "Open Items" below for
  full detail. Two were genuine Indicator-repo script bugs (scripts
  written for the old, pre-Packager manual deployment convention, never
  adapted to the real Contract-generated Release shape); one was a
  serious Packager bug (`docker_build.py`'s image export silently
  dropped repository/tag info — `docker-py`'s own docs say the default
  does this — so a genuinely separate Docker Engine loaded every
  archive completely untagged, and `docker compose up` fell back to a
  registry pull that fails offline). The Packager bug affects **every
  Release ever produced**, not just Indicator's — see below.
- **Phase 5 (Verify)**: PASS — real `verify_installation.sh`, both
  containers healthy, backend `/health` returned healthy, frontend
  HTTP 200.
- **Phase 6 (Restart check)**: PASS — real `stop_stack.sh` +
  `start_stack.sh` cycle, both containers came back up healthy
  unattended, full re-verification passed again.

**Not yet done**: committing the three Packager fixes (currently only on
this machine, tested, 186/186 passing) and the Indicator script fixes
(committed locally to Indicator's own repo, not yet pushed) — holding
for explicit go-ahead per this project's git discipline. Also not yet
done: re-verifying P8's earlier HCopilot "final clean pass" against this
same image-tag bug — that proof never did a genuine cross-machine
`docker load`, so it's likely affected too; P9's fleet retest will
naturally re-surface this for all 5 apps.

Platform track: `PL0` through `PL9b` done and tested (see "Period A —
Platform" below for the real, slice-by-slice detail). `PL9b` (Offline VM
Acceptance) ran the full 23-step Offline Acceptance Scenario for real on
the genuinely air-gapped Offline Validation VM, found and fixed a real
`RECOVER`-availability gap live, and closed the entire Platform track's
Period-A Exit Gate — no Platform work remains open.

## Open Items (status as of 18/08/2026, verified directly — not relayed)

**Packager fixes, done the same day, not yet pushed:**

- **`RC-SCR-005`** — fixed. Not a filesystem permission issue but a git
  *index mode* issue (git's own tracked executable-bit flag for a file,
  independent of the real filesystem permission) — corrected for all 10
  of Indicator's scripts, **committed and pushed** to Indicator's own
  repo. While at it, the same underlying issue was found and fixed
  proactively in **Voice Project (29 scripts)** and **HCAT (11 scripts)**
  too — HCopilot and STT-SCHEDULE already had it right.
- **`RC-OFF-002` sibling-image gap** (HCopilot's `db-init` service
  reusing `backend`'s image instead of building or pulling its own) —
  fixed. A service with no `build:` key isn't always an external
  prebuilt image; it can be reusing a sibling service's build output.
  Detected by cross-referencing image tags before deciding to pull;
  wired into the compose-rewrite step; tests added and passing; verified
  with a real rebuild against HCopilot.
- **Model-artifacts feature** — built and confirmed working against real
  HCopilot: computes a `checksum` and resolves `baked_into_image` for a
  declared model artifact, replacing the previous unconditional "not
  supported" rejection. Required a real, scoped extension to
  `engineering-answers.json`'s schema (`source_path`, `service` per
  artifact) — not a change to the frozen Release Contract itself.
  Building this surfaced and fixed two more real, previously-unknown
  bugs:
  - A placeholder-detection gap — `__GENERATE_ME__` wasn't recognized as
    a placeholder value, only `change`/`your`/`todo`/`sample`/etc.-style
    markers were.
  - A staleness-loop bug — the Packager's own `--output` directory,
    conventionally nested inside the project being packaged, wasn't
    excluded from the project's own inspection walk, so its own
    generated output was silently changing the very fingerprint used to
    detect staleness.
- **STT-SCHEDULE / Voice Project / HCAT model-baking fixes** — done,
  committed. All three apps now bake their model into the image at build
  time instead of bind-mounting it at runtime, matching the platform
  rule below. **Pushed**: STT-SCHEDULE (`offline-deployment` branch,
  not yet merged to `master`) and Indicator (`master`, no separate
  branch needed — no database/model at all). **Not yet merged to
  `main`**: Voice Project and HCAT, both on an unmerged
  `bake-whisper-model` branch (13 and 1 commits ahead, respectively) —
  deliberately held per the agreed branching policy (merge only once a
  real `rah package` end-to-end pass confirms the fix), see the
  `ticklish-marinating-unicorn` plan file.
- **The "everything must be inside the image by build time" rule** —
  confirmed merged into the real, canonical `6. RAH Application
  Engineering Playbook.md` in the Obsidian vault (verified directly:
  present as new §11a in the long-form Dockerization prompt and §7a in
  the compressed form). **This repo's own mirrored copy at
  `docs/rah-lab-standards/6. RAH Application Engineering Playbook.md`
  has NOT been updated to match** — confirmed absent there too. Needs a
  follow-up sync pass, copying the real merged text over rather than
  reconstructing it.

**Sync gap — not a code problem:** all five Packager fixes above exist
only on this Windows checkout right now (except where explicitly noted
pushed above). `git fetch` confirms nothing new has arrived from
elsewhere for the Packager side. Needs a commit + push here before this
checkout's own history (and any other checkout, e.g. `or-stt`) reflects
any of it.

**P8's final clean pass against real HCopilot — confirmed for real,
19/08/2026.** Docker Desktop was hung on this machine at session start
(CLI unresponsive, stale `docker` processes going back hours despite the
WSL2 `docker-desktop` distro reporting "Running") — fixed with a full
Docker Desktop quit + `wsl --shutdown` + relaunch, confirmed via a real
`docker version` round trip before proceeding. Getting to the actual
clean pass then surfaced **two more real, previously-unknown bugs**,
both fixed at root cause:
- **A staleness self-invalidation loop**, distinct from the already-
  documented `--output`-directory bug above. `compute_inspection_fingerprint()`
  hashed the *entire* `ProjectInspectionResult`, including the
  `packager_state` category — which every successful `rah package` run
  itself mutates (`project-state.json` gains a new `release_history`
  entry). So a successful Release permanently invalidated its own
  just-used engineering answers for the very next run, even with zero
  real engineering change. Fixed in `engineering_answers.py` to exclude
  `packager_state` from the hash; regression test added; 184/184 tests
  pass.
- **A bad Claude-generated engineering answer**, caught by
  `validate-answers`' cross-consistency check, then by `RC-DB-002` itself
  after a first correction attempt undershot: `database.migration.entrypoint
  = "backend/alembic"` didn't match any script P2 actually discovered.
  Investigated the real `update_offline.sh` directly rather than
  guessing — HCopilot's Alembic migrations run automatically inside
  `db-init`'s own container command during `docker compose up
  --force-recreate`, with no separate invocable entrypoint at all.
  Corrected `database.migration.required_for_update` to `false` (the
  honest answer: no distinct entrypoint is required because none exists,
  not a workaround).

Final result: `rah package` → `overall_result: PASS`, real finalized
`HCopilot_Release_1.0.1`, all 3 declared images archived (backend,
frontend, **and** the `sqlserver` prebuilt base image — `RC-OFF-002`
passes for HCopilot now, unlike the documented P7 HCopilot proof where
it correctly failed), checksums and Compliance Report both written. P8
is now DONE, not just built — this is the first real confirmed clean
pass, live-proven, not assumed.

**Re-verified against P7's image-tag export bug, confirmed clean,
20/08/2026.** This `HCopilot_Release_1.0.1` proof predated the
image-tag-export fix found later during P7's Phase 4 — genuinely
suspect, since that bug affected every Release ever produced. Re-ran
`rah package` against real HCopilot with the fixed code:
`overall_result: PASS`, real finalized `HCopilot_Release_1.0.2`. Then a
real, direct proof rather than trusting the Compliance Report alone:
force-removed all three images from the local Docker image store
(`docker rmi -f`, "Untagged" only — the underlying image data for
`rah-hcopilot-backend`/`frontend` stayed cached under their `1.0.0`/
`1.0.1` tags from earlier session work, a real instance of the exact
multi-tag-history scenario the export fix specifically had to handle;
`mcr.microsoft.com/mssql/server` was fully removed, no other tags left),
then `docker load`ed all three archives fresh. All three restored their
exact correct tags — `Loaded image: rah-hcopilot-backend:1.0.2`,
`rah-hcopilot-frontend:1.0.2`, `mcr.microsoft.com/mssql/server:2022-latest`
— confirmed again via `docker images`. The fix holds for HCopilot across
both code paths (built images and the pulled/prebuilt base image).

**P9 (Full Fleet Validation) DONE — all 5 real apps PASS, confirmed
20/08/2026.** This is the real evidence for the Period A Packager Exit
Gate: five structurally different real hospital applications (no
database, SQL Server, Postgres, single-repo, cross-repo, single-model,
six-model) all independently packaged into Contract-compliant Releases
by the same unmodified Packager code, zero per-app branching. Full
results tracked in the Slicing Task Table. HCopilot PASS, Indicator PASS
(full Phases 1-6), STT-SCHEDULE PASS, Voice Project PASS, HCAT PASS.
STT-SCHEDULE and Voice Project
each surfaced one more bad Claude-generated answer (same root-cause
family as HCopilot's original migration-entrypoint finding) plus one
more real, generic Packager bug each: `rc_cfg_002`'s placeholder
detector was scanning comment lines, not just real assignments (fixed
to mirror `rc_cfg_001`'s already-correct convention — found via
STT-SCHEDULE's real port-checking comment); `rc_off_004`'s "public URL"
detector didn't distinguish a bare Docker Compose service name (e.g.
`http://whisper`) from a real public domain (fixed: a hostname needs at
least one dot to ever resolve on the public internet — found via Voice
Project's real internal `WHISPER_SERVICE_URL`). 190/190 tests pass.

**HCAT (5th of 5) — PASS, confirmed for real**, after a genuine
multi-hour block on an Anthropic API usage limit resolved mid-session.
Further than HCAT's "deferred, multi-model complexity" reputation
suggested: `rah inspect` handled the real, hundred-plus-file repo
cleanly, and `rah prepare-answers` correctly discovered and pathed all 6
real declared model artifacts on the first try. Two more real bugs found
and fixed: a genuine `RC-SCR-005` regression in HCAT's actual repo (14
scripts in a *newer* release folder committed non-executable — the
earlier documented fix was real but for an older, superseded folder —
fixed for real, committed and pushed to HCAT's own `bake-whisper-model`
branch), and one more placeholder-marker gap (`__SET_ME__`, same family
as `__GENERATE_ME__`, fixed generically). 191/191 tests pass. Final
result: `rah package` → `overall_result: PASS`, real finalized
`HCAT_Release_1.0.0` — `sqlserver` (pulled), `db-init`, `backend` (1.37
GB, 6 baked ML models — the largest archive across all 5 apps this
session), and `frontend` (built via a genuine cross-repo relative
Compose context, `../Front_End_Feedback_Analysis`, both repos cloned as
siblings for the test). All 4 images re-verified against the image-tag
export bug via force-remove + reload. Full detail in the Slicing Task
Table's P9 section.

**P7's Real Manual Acceptance Test, Phases 2–6 against Indicator — ALL
PASSED for real, 20/08/2026.** The first full end-to-end pass this test
has ever achieved. Getting through Phase 4 (Install) surfaced three real,
previously-unknown bugs, each found by genuine execution failure, not
inspection — fixed at root cause, not worked around:

- **Packager bug, serious, affects every Release ever produced**:
  `docker_build.py`'s `_export_one_image()` called `image.save()` with no
  arguments. `docker-py`'s own docstring says plainly: the default
  (`named=False`) "will not retain repository and tag information for
  this image." Every prior live-proof only ever reloaded an export back
  into the *same* Docker Desktop installation that built it, which never
  surfaced this. A genuinely separate Docker Engine (the offline VM)
  loaded every archive as completely untagged, so `docker compose up`
  couldn't find the image locally and fell back to a registry pull —
  which fails offline, the exact failure mode the whole Contract exists
  to prevent. This also retroactively explains an already-documented but
  only partially-understood P7 finding (RC-ART-008's "OCI-format
  archive, `RepoTags: null`" observation) — that was already evidence of
  this exact bug, not a separate cosmetic format quirk. First fix attempt
  (`named=True`) was itself insufficient: it picks `image.tags[0]`, and a
  content-addressed image ID accumulates every tag it was ever
  built/pulled with across repeated runs (nothing untags the previous
  version automatically) — a second real bug, found immediately after
  the first fix, when a stale prior version's tag got embedded instead of
  the current Release's. Final fix: pass the exact, already-known tag
  reference explicitly (`image.save(named=image_ref)`) rather than
  relying on list order. Two new regression tests strengthen the existing
  same-installation round-trip tests (which never asserted `.tags` at
  all — the actual gap that let this ship undetected) plus one new test
  that reproduces the multi-tag scenario directly. 186/186 tests pass.
  **This means every Release the Packager has ever produced, including
  P8's HCopilot proof above, likely has this same bug baked in** — never
  caught because no prior proof ever did a genuine cross-machine
  `docker load`. Not yet re-verified for HCopilot; P9's fleet retest
  will naturally re-surface it.
- **Packager bug, generic**: `construct_release.py` copied only the
  individually-declared entrypoint file for each `deployment.entrypoints`
  field, never any sibling files it might `source`. Indicator's real
  `install_offline.sh` sources a shared `_common.sh` helper that no
  manifest field ever names — `RC-SCR-005` passed (the script is
  syntactically valid and executable) but real execution failed with "No
  such file or directory" the moment it tried to source its own helper.
  Fixed by copying every file in a script-like entrypoint's own source
  directory (not just the one named file) into whichever Release
  subdirectory(s) draw from it, deduplicated per (subdir, source
  directory) pair — confirmed correct for the case where the same source
  script is copied to two different destinations (`deployment.entrypoints.verify`
  and `verification.entrypoint` both point at the same file). One new
  regression test.
- **Two real Indicator-repo script bugs**, not Packager bugs — the
  scripts were written for the old, pre-Packager manual RAH-OIP
  deployment convention and never adapted to match what `rah package`
  actually produces: `COMPOSE_FILE` referenced `docker-compose.offline.yml`
  in 8 places (the Packager always generates `compose/docker-compose.yml`,
  fixed by the Contract); `load_images.sh` hardcoded `backend.tar`/
  `frontend.tar` (the Packager names archives
  `rah-{slug}-{service}_{version}.tar`, version embedded on purpose so
  Release versions never collide — rewritten to load every `*.tar` under
  `docker-images/` instead of assuming fixed names); the config template
  copy referenced `compose/.env.offline.template` instead of the real
  `configuration/.env.offline.template`. All fixed and committed locally
  to Indicator's own repo (not yet pushed).

Full Testing Record for all 6 phases:
`docs/development/Period A — Independent Product Development;
Packager/3. Real Manual Acceptance Test — Results.md`.

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
against the real Anthropic API with the engineer's real key).
**P4 DONE** (Release Planning). `rah plan` previews exactly what Release
would be built — application, proposed version, output directory name,
expected Docker images/release directories, required scripts/configuration
— without writing anything, by combining P1's Project Version State, P2's
inspection, and P3's validated engineering answers. No new persisted
artifact, so no new frozen schema, unlike P1/P3. Four blocking conditions,
each a real structured error: project not initialized, dirty Git state
(user-confirmed: no override policy in V1), duplicate version, and
missing/invalid/stale engineering answers (reuses `validate_answers()`
directly rather than re-implementing that logic). 14 new tests, 122/122
total pass, live-proven against the real built container including the
dirty-state rejection.
**P5 DONE** (Docker Build and Artifact Preparation). `rah build` builds
every Compose service that declares its own `build:` context, tags it
(`rah-{application_slug}-{service}:{version}`, matching the architecture's
own manifest example verbatim), exports it to a `.tar` archive, and
reports a per-service build inventory — the first slice doing real,
expensive external operations, not just reading/parsing. Deliberately
scoped down to "internal capabilities" per the spec's own wording: no
dependency on Project Version State (`application_slug`/`version` are
caller-supplied), and only services with their own `build:` key are
built — a prebuilt `image:` reference is reported but not built/exported
(out of this slice's scope). Two new errors: `PKG-DOCKER-BUILD-FAILED`
(carries the failing service + real build-log tail) and
`PKG-DOCKER-IMAGE-EXPORT-FAILED`. Fails fast, leaving a real partial
build workspace on failure — never treated as a finalized Release. 7 new
tests, 129/129 total pass, all against the real Docker Engine (no mocks).
Live-proven against the real built container: a trivial fixture end to
end including a real `docker load` round-trip on the exported archive,
and real, full builds against **both** required acceptance apps —
HCopilot (explicit `context`/`dockerfile` Compose form, real
apt/pip-heavy backend build, ~496 MB archive) and Indicator (shorthand
`build: ./service` Compose form, ~144 MB archive) — both succeeded for
real, proofs cleaned up afterward.
**P6 DONE** (Release Construction — "where previous pieces finally
combine"). `rah construct` assembles a temporary candidate Release
directory per `release-layout.yaml`, generating `release.yaml` from
Project Version State + Inspection Result + validated Engineering
Answers + Build Artifact Metadata + Release Plan, all five P1–P5 inputs
combined for the first time. `RELEASE_MANIFEST_SCHEMA` embedded verbatim
from the real, frozen `contracts/1.0/release-manifest.schema.json` (a
dedicated test asserts zero drift from the real file, structurally).
Rewrites the app's own `docker-compose.yml` so `build:` stanzas become
`image:` references to the images `rah build` actually produced — the
Release ships pre-built images, not source. Three new real gaps between
"structurally valid engineering answers" (P3's own bar) and "enough to
construct a Release" resolved as explicit, named blocks rather than
silent defaults: missing `verification.entrypoint`, configuration inputs
declared with no template, and declared model artifacts (models require
computing `baked_into_image`/`checksum`, deliberately unimplemented —
matches HCAT's own deferral). `docker.images[]` only includes services
P5 actually built, a known, documented scope gap (same as P5's own).
Unconditional overwrite re-run behavior, same precedent as
`rah prepare-answers`. 17 new tests, 146/146 total pass, including a
dedicated `RC-REPRO-001` reproducibility test (construct twice, diff
everything except `release.created_at` and image archive bytes).
Live-proven against the real built container with real, full candidate
Releases for **both** required acceptance apps: HCopilot (real Claude-
generated answers caught by the existing `validate-answers` consistency
gate on the first, unedited attempt — Claude answered two database
entrypoints with inline shell commands instead of script paths; corrected
by omitting them, both optional — then a full real candidate Release:
2 real images, real compose rewrite, real manifest, `verification.entrypoint`
and all documentation resources present) and Indicator (same story:
first attempt correctly rejected — no lifecycle scripts exist in the
real repo at all, Claude's `docker-compose.yml` fallback correctly didn't
match; corrected, then blocked again by a real, separate finding — the
real Indicator repo's Dockerfiles are uncommitted local WIP that a
disposable `git clone` never picks up, `PKG-DOCKER-BUILD-FAILED` reported
it cleanly rather than crashing — copied the real Dockerfiles in,
succeeded). Also found and worked around, not a Packager bug: Windows
host git (`core.autocrlf=true`) vs. the container's Linux git disagree on
every line ending in a `git clone`d repo, making every file look
"modified" from inside the container even though nothing changed —
documented as a real environmental gap (extends P0's "container-only"
finding to Git behavior, not just Docker connectivity), worked around
per-repo via `git config core.autocrlf true` + `git checkout -- .` run
from inside the container.
**P7 AUTOMATED PORTION DONE** (Validation, Finalization and Independent
Offline Proof — the Period A Packager finish line's automated half).
`rah package` turns a P6 candidate into a finalized Release: all 56
mandatory RC-* rules from `validation-rules.json` (everything except
`RC-REPRO-001`, which the Contract itself excludes from
`validation_order` — a build-time regression check comparing two
candidates, covered by P6's own reproducibility test instead), checksums
(`checksums.py`, sha256sum-CLI-compatible, plus a Release fingerprint —
COMPLETED as sha256 of `release.yaml`'s own bytes to avoid a circular
dependency against RC-INT-004's mandated closure order), a Compliance
Report (`compliance_report.py`, schema embedded verbatim with the same
drift test as P6's manifest), and a Project Version State update that
happens only after everything else succeeds. `rah validate`
independently re-validates any Release directory afterward, no source
project required. 33 new tests, 169/169 total pass, all real Docker
builds. Live-proven against the real built container: a minimal fixture
through a full `rah package` → `rah validate` round trip including real
post-finalization tampering correctly detected as `FAIL` and a real
read-only re-validation degrading gracefully; then real HCopilot end to
end, surfacing three real bugs (P6 itself missing required directories;
two RC-* rules checking closure-generated files too early; an OCI-format
Docker archive assumption; a placeholder-detection false positive on a
real `.env.offline.template`) and two real Windows-bind-mount findings
(executable bits not propagating through `git checkout` at
`core.fileMode=false`; `core.autocrlf=true` fixing `git status` but not
actually producing LF content, refining rather than reversing the
earlier P4/P6 CRLF finding) — all fixed at their root cause. Final,
clean HCopilot run: every rule passes except the already-documented
`RC-OFF-002` (prebuilt base images like `sqlserver` aren't bundled
offline, a known P5/P6 scope gap) — correctly and honestly rejected, not
papered over. **Real Manual Acceptance Test executed 2026-08-11, FAILED at
Phase 1**: real Indicator app, real Legion/`or-stt`/offline-VM lab
hardware — `rah package` built two real Docker images and a full
candidate Release, then correctly refused to finalize it at `RC-SCR-005`
(Indicator's lifecycle scripts committed without the executable bit — a
real Indicator-repo gap, not a Packager bug). Phases 2–6 not reached in
this first attempt; the offline VM was never touched. Full Testing
Record: `docs/development/Period A — Independent Product Development;
Packager/3. Real Manual Acceptance Test — Results.md`.

**`P8` (Model Artifacts & Offline-Completeness Closure) DONE**, and
**the Real Manual Acceptance Test subsequently passed all 6 phases for
real, 2026-08-20**, closing out the Packager side of Period A in full.
This section stops narrating slice-by-slice detail here rather than
duplicate it a third time (it already lives in full above, under
"Current Phase," and in
`docs/development/Period A — Independent Product Development;
Packager/2. Initial Slicing Task Table.md`, this project's actual
per-slice source of truth) — see either for the complete story,
including the three real bugs found and fixed during the Real Manual
Acceptance Test's Phase 4 (one serious: an image-tag export bug
affecting every Release the Packager had ever produced) and `P9`'s
subsequent full-fleet retest (all 5 real apps PASS).

**Packager Period A Exit Gate: satisfied.** "A real application can be
initialized, inspected, assisted through Claude, planned, built,
packaged, validated, finalized, manually installed offline, and a
second Release can be produced without corrupting version history" —
demonstrated for real against Indicator (all 6 phases) and confirmed
across the other 4 real apps via `P9`. Two loose ends remain, neither
part of the Exit Gate itself: the Playbook §11a/§7a mirror-sync (see
"Future Design Tasks" / Open Items above), and merging the
STT-SCHEDULE `offline-deployment` branch (paused — real merge conflicts
with `master`'s own in-progress work, handed off to a session with more
context on that repo).

## Period A — Platform

Status: **Slicing proposal reviewed and accepted** (`PL0`–`PL9`, same
rigor as the Packager review). Findings: boundaries sound overall; `PL8`
(Backup/Update/Recovery) and `PL9` (UI/Offline Acceptance) are tracked as
paired sub-slices (`PL8a`/`PL8b`, `PL9a`/`PL9b`) for testing-signal
reasons; `PL3`/`PL4` each got one clarifying implementation note. No
redesign, no new V1 capability. **`PL0` (Runtime, Database & Test
Foundation) is DONE** — `platform/` (FastAPI + SQLAlchemy/Alembic +
`docker` SDK), real Docker Compose deployment (backend + PostgreSQL 16) on
this Online Debian VM, all 8 required proofs verified live against the
real built container, including both failure paths (PostgreSQL stopped →
`503`/`PLT-DATABASE-003` without a backend crash; Docker socket unmounted
→ `503`/`PLT-DOCKER-001`). **`PL1` (Generic Operation Framework) is DONE**
— canonical `operations`/`operation_events`/`operation_logs` tables
(migration `0002`), the application-operation lock enforced as a
Postgres partial unique index (race-free by construction, not
application-level locking logic), stale-operation detection, and
`GET /api/v1/operations/{id}` + `.../events` + `.../logs`, all built
against a synthetic test operation per the plan (no real Application/
Release exists yet — that's `PL3`). 42/42 tests pass total, all 11
required `PL1` proofs verified live against the real running Compose
container. **`PL2` (Release Discovery) is DONE** — `scan_releases` /
`list_candidates` / `get_candidate` against the real
`tests/fixtures/releases/` Golden Fixtures (`valid-release-1.0.0`,
`incomplete-release.partial`, `missing-manifest`, `malformed-manifest` —
all four the plan names), `release_candidates` table upserted by
`directory_name` so repeat scans never duplicate, and
`POST /api/v1/release-candidates/scan` + two `GET` endpoints. Also fixed:
FastAPI/Pydantic request-validation failures were bypassing the common
response envelope since `PL0` (never triggered until `PL2`'s
`extra="forbid"` check) — now wrapped consistently as `PLT-INPUT-003`.
59/59 tests pass total, all 8 required `PL2` proofs verified live against
the real running Compose container using the real fixtures. **`PL3`
(Release Import and Registry) is DONE** — real `applications`/`releases`/
`release_storage` tables (migration `0004`, plus the FK from
`operations.application_id` that `PL1` deferred), `import_release()`
re-validating manifest schema (against the real, mounted Contract
schema — no embedded copy), Contract version, Compliance Report,
checksums, fingerprint, and architecture/Platform compatibility, while
trusting the Compliance Report for everything else per §3.5. 8 real
Golden Release fixtures built and schema-verified. Real dependency gap
recorded: `PL3` also depends on `PL1` in practice (import uses the
Operation Framework per §7.12), which the original Master Matrix's
`Depends On` column omitted — harmless since `PL1` already precedes
`PL3` in the slice order, just noted rather than silently fixed. Also
closed a gap `PL2`'s own write-up had flagged: `scan_releases` now
cross-checks the real Registry and correctly reports `ALREADY_IMPORTED`/
`IDENTITY_CONFLICT`. 76/76 tests pass total, all 9 required `PL3` proofs
verified live against the real running Compose container, including the
full accept/reject matrix (1 successful import, 3 correctly `FAILED`
operations, 1 correctly-untracked rejection) leaving exactly the right
Registry state and nothing more. Deliberately independent of the
Packager track throughout — no Packager output involved anywhere.
**`PL4` (Application State and Action Intelligence) is DONE** —
`application_query.py`, a minimal `deployments` table +
`applications.active_deployment_id` (migration `0005`, no lifecycle
script ever writes it here — `PL4` is read-only, its own tests seed it
directly per the pre-PL0 review's own anticipation of this exact gap).
Real, evidence-based decision logic for
`INSTALL`/`UPDATE`/`DOWNGRADE`/`REINSTALL`/`VERIFY`/`BACKUP` (`RECOVER`
correctly always unsupported — no failure-tracking exists until `PL8`).
`operational_health` honestly reports `UNKNOWN` for any installed
application, never a fabricated `HEALTHY`, since no real host
verification exists until `PL7`. 98/98 tests pass total, all 8 required
`PL4` proofs verified live against the real running Compose container,
combining a real imported Golden Release with direct Registry seeding
for the installed-state half. **`PL5` (Deployment Planning and
Configuration) is DONE** — `deployment_planning.py`
(`prepare_installation`/`prepare_update`/`validate_deployment_inputs`/
`suggest_available_ports`) plus `deployment_configuration` (migration
`0006`). Port checks are real `socket.bind()` calls against this host,
not simulated. `prepare_update` reuses `PL4`'s `get_available_actions()`
directly for transition validity rather than re-deriving it — the two
now provably agree by construction. Secret-flagged configuration inputs
never carry a `current_value`, fresh or preserved, only `value_state`.
Along the way, `application_query.py`'s three lookup helpers were
promoted from private to shared internal functions since `PL5` genuinely
needed them — no behavior change, full suite green before and after.
113/113 tests pass total, all 10 required `PL5` proofs verified live
against the real running Compose container, including a real update plan
showing real preserved configuration and an explicit mandatory-backup
requirement. **`PL6` (Fresh Installation Execution) is DONE** — the
Platform's first operation that actually changes host/Docker state.
`installation.py`: synchronous request/lock validation, then real
execution in a background thread (real `202` → poll → `SUCCEEDED`/
`FAILED`, matching §5.3). Real Docker images replaced the placeholder
tars in the Golden Fixtures; the backend image needed the real `docker`/
`docker compose` CLI added (a real infrastructure gap found and fixed,
not worked around — the Platform invokes Manifest-declared scripts
rather than reimplementing their behavior, per §12.6). Minimal
verification is real Docker container inspection only — the Release's
own `verify_deployment.sh` stays `PL7`'s job. A real cross-slice bug was
found and fixed: `PL5`'s `validate_deployment_inputs` had grown a live
port check that duplicated `PL6`'s own dedicated recheck and produced
the wrong error for the Port Conflict test — removed from `PL5`, kept
only in `PL6` where architecture actually places it (§3.7). 122/122
tests pass total, all 8 required `PL6` proofs verified live against the
real running Compose container — including confirming the installed
container from *outside* the backend container, on the real host's own
Docker Engine, and `PL4`'s action logic correctly flipping to reflect a
*real* installation for the first time, not seeded state.
**`PL7` (Verification and Host Reconciliation) is DONE** — `verification.py`
completes the three-authority model (Manifest = expected, Registry =
recorded, Host Inspection = observed). `PL6`'s `_minimal_verify()` is
retired; `installation.py` now calls the same real `run_verification()`
a standalone `POST .../verify` call uses, so the two paths can never
diverge. Real check set: `release_identity`/`container_existence`/
`container_health`/`image_tags`/`selected_port`/`offline_runtime`/
`persistent_configuration` mandatory, `database_connectivity`/
`migration_state`/`backend_health`/`frontend_reachability` honestly
`NOT_APPLICABLE` unless a Release declares them required — never a
fabricated `PASS`. New schema (migration `0007`): `verification_runs`/
`verification_checks` (every run preserved independently, §7.25) and
`reconciliations` (recorded drift, §7.27). Reconciliation logic reaches
all five real states (`UNKNOWN`/`CONSISTENT`/`PARTIALLY_RUNNING`/
`DRIFT_DETECTED`/`UNREACHABLE`) against genuine Docker state changes,
not mocks. Two real bugs found and fixed before shipping: (1) a
pre-existing, `PL6`-era fixture bug — `install-with-secret`'s manifest
still declared the wrong image repository (only the Compose file was
corrected back in `PL6-I02`) — caught by `PL7`'s own new `image_tags`
check, not introduced by it; (2) `_resolve_expected_release` returned a
deployment id instead of resolving the real release id, fixed with a
dedicated regression test. One deliberate, flagged deviation from
architecture's literal text: `POST .../verify` runs synchronously
(`200`), not `202` + poll — verification is a handful of fast checks,
not a long-running script. 143/143 tests pass total, all 9 required
`PL7` proofs verified live against the real running Compose container
through a full scan → import → install → verify → host-state →
reconcile cycle, including real drift detection after manually stopping
the container from *outside* the backend container on the host's own
Docker Engine. **`PL8a` (Backup and Update, the first of two tracked
`PL8` sub-slices per the pre-PL0 review) is DONE** — `backup.py`/
`update.py` implement the second major lifecycle transition (existing
application → new Release, configuration/data preserved). Real
sequencing per §9.19/§9.22/§9.26: `BACKING_UP` (shares the parent
`UPDATE` operation's own `operation_id`, per architecture's "Shared
Operation for Sub-Steps") → `EXECUTING_SCRIPT` → `MIGRATING` (real
script, real captured exit code as migration evidence) → `VERIFYING`
(reuses `PL7`'s `run_verification` wholesale) → `RECORDING_RESULT`
(only after a real `PASS` — an unsuccessful update never overwrites the
last known successful active-deployment record). New schema (migration
`0008`): `backups`. Configuration preservation is real: a preserved
secret's actual value is read back from the previous deployment's real
rendered `.env` (the Registry itself never stores secret plaintext, only
`secret_reference`) via a new `installation.read_rendered_env` helper.
A real, necessary amendment to `PL7`'s `verification.py` was required:
an update's own `POST_UPDATE` verification runs *before* the Registry
commit, so two of `PL7`'s checks needed a `verification_type` parameter
to stop treating the still-pointing-at-the-source Registry state as
drift. Two real bugs found and fixed before shipping (both in this
slice's own new code, not `PL7`'s): a config-validation helper that
re-checked preserved string values against strict Python types, and two
tests that wrongly expected a raised exception from an async (`202`)
entry point. 14 new tests added (157/157 total passing), all 7 required
`PL8a` proofs verified live against the real running Compose container
through a full scan → import → install → update cycle, including
confirming the real container now running the target image from
*outside* the backend container.
**`PL8b` (Recovery, the second `PL8` sub-slice) is DONE** — `recovery.py`
implements §7.24 (Recovery History Rule): recovery always creates its
own, separate operation record, never rewriting the failed operation it
recovers from. A deliberately simple, real design: recovery never
changes *which* Release is active, only repairs the *host* back to what
the Registry already, correctly, still claims — §9.22 already
guarantees a failed `INSTALL`/`UPDATE` never falsely overwrote the
active-deployment record, so `_perform_restore` always targets the
*currently active* deployment and never calls `commit_deployment`.
`PL4`'s `_evaluate_recover()` — previously a correctly-reasoned
permanent stub ("no failure-tracking exists until PL8") — now has real
logic: `RECOVER` is allowed exactly when the application's most recent
`INSTALL`/`UPDATE` operation is `FAILED`. A real bug caught by the test
itself, not by inspection: the first draft of `valid-release-1.0.0`'s
new restore script only restored configuration, not the actual
container — insufficient for the real "verification failed after the
update script already swapped the container" scenario, caught because
`reconcile_application_state` still reported `DRIFT_DETECTED` after a
"successful" recovery; fixed with a real, complete restore (`docker
load` + `docker compose up` against the *active* deployment's real
`.env`). 6 new tests added (163/163 total passing), all required proofs
verified live against the real running Compose container — including a
real failed update genuinely flipping `RECOVER` from `false` to `true`,
and a real recovery repairing real host drift back to `CONSISTENT`
while the original failure remains visibly `FAILED` in history.
**`PL9a` (Operator UI Integration, the first of two tracked `PL9`
sub-slices) is DONE** — a real React 19 + TypeScript + Vite +
TailwindCSS v4 + shadcn/ui (Radix) + TanStack Router/Query + React Hook
Form + Zod UI at `platform/frontend/`, matching the UX architecture
spec's exact dark palette, layout, and screens. Every screen is wired to
the real API, no mocked data: Dashboard, Platform (scan/import),
Applications, Application Details (`Overview`/`Releases`/`History`/
`Settings`), a real 4-step Installation Wizard, an Update flow, a
reusable `ProgressView` (live log, auto-scroll), and an
`ErrorPresentation` component covering the full `PLT-*` catalog with
Title/Possible Cause/Suggested Action/collapsed Technical Details —
never a raw exception. One real backend gap found and closed (not
approximated client-side): added `GET /api/v1/operations` (cross-app
listing) with 2 new tests (165/165 backend tests passing). Every
required user journey was live-driven with a real headless browser
(Playwright) against the real backend — Dashboard, Release Import
(success and a real `PLT-INTEGRITY-002` error path), Fresh Install (real
`docker load`+`compose up`, real container confirmed via `docker ps`
from outside the backend container), History — catching one real bug
(a cache-invalidation gap that hid a genuinely-succeeded `Verify`
operation from the "Recent Operations" panel) before it shipped. Also
found and fixed, mid-slice, a real host-level infrastructure fault
unrelated to this session's own work: Docker's default bridge went down
due to the Windscribe VPN client's kill-switch nftables rules
conflicting with Docker's NAT rules, diagnosed from scratch (with the
user running sudo diagnostics) down to the exact conflicting chains and
fixed by disconnecting the VPN — this had been silently blocking the
entire backend test suite, not just PL9a's own work. The frontend is
also genuinely deployable, not just a dev server: a multi-stage
Dockerfile (`npm run build` → nginx) wired into `docker-compose.yml` as
a new `frontend` service, live-verified serving the real production
build and correctly proxying real API calls through the Compose
network.
**`PL9b` (Offline VM Acceptance, the second `PL9` sub-slice) is DONE** —
the plan's own full 23-step Offline Acceptance Scenario run for real on
the genuinely air-gapped **Offline Validation VM** (`10.10.10.2`, no
gateway, real Hyper-V lab hardware): fresh install of `1.0.0`, update to
`1.1.0` with a real mandatory backup, deliberately introduced host
drift, detection, and controlled recovery — all real, none of it
simulated. Images built where there's real internet (`or-stt`),
transferred via `docker save`/`scp`/`docker load` only, matching the
lab's own offline-transfer standard. Handled a real shared-VM complication
twice (unrelated, currently-running work from other concurrent teams
landed on the same VM mid-slice) by stopping and confirming with the
user before any revert, rather than assuming exclusive access. Found and
fixed a real, substantive gap live: the plan's own drift-with-no-failed-
operation scenario exposed that `RECOVER` was permanently unreachable
unless the *most recent* lifecycle operation had itself failed — fixed
in `application_query._evaluate_recover()` (now also unlocked by a
recorded `DRIFT_DETECTED`/`PARTIALLY_RUNNING`/`UNREACHABLE`
reconciliation) and `recovery.recover_application()` (`failed_operation_id`
now genuinely optional), 167/167 tests passing, then re-verified live on
the offline VM a second time after the fix. Confirmed the same backend
evidence appears through the frontend's own nginx proxy as through the
direct API, closing `PL9a`'s own equivalence claim against a real,
`docker load`-transferred image on a physically separate machine. This
completes the entire Platform track — every item in the proposal's own
Period-A Platform Exit Gate, including "Entire scenario works in Offline
Debian VM," is now real, tested, evidence-backed. See
`docs/development/Period A — Independent Product Development;
Platform/2. Initial Slicing Task Table.md`.

## Period B — Integration

Status: **STARTED — `B0`, `B1`, `B2` DONE, urgent interstitial fix `B2+` DONE** (2026-08-21), `B3` (retry) next. Entry Gate met (2026-08-20): `docs/development/Period B — Cross-Product Integration/1. Initial GPT Proposal.md` (lines 43–79) requires both Period A tracks to independently pass their own Minimum Gate before Period B may begin — not "development has progressed far enough," an explicit gate. Both are now real, evidence-backed, not assumed:

- **Packager Minimum Gate** — met: init, inspect, validate engineering answers, plan, build Docker artifacts, construct, validate against the Contract, finalize, produce a stable Release fingerprint, produce a Release that can be manually installed offline. All demonstrated for real, most recently via the 6-phase Real Manual Acceptance Test against Indicator and the `P9` full-fleet retest (5/5 real apps).
- **Platform Minimum Gate** — met: scan Golden Releases, import them, represent Applications/Releases correctly, plan installations, install a Golden Release, verify it, update between compatible Golden Releases, preserve backup/history, detect failures and drift, expose operation results via the API. All demonstrated for real via `PL0`–`PL9b`, most recently the real 23-step Offline Acceptance Scenario on the genuinely air-gapped Offline Validation VM.

**`2. Initial Slicing Task Table.md` written, 2026-08-20** — the same
Master Matrix + pre-implementation review both Period-A tracks got before
their own `P0`/`PL0`, adapted for Period B. Two real revisions to the
proposal's own slice map: `B5` (Update Path) upgraded from a single
`A → B` transition to a real 3-version `A → B → C` chain (two update
hops, not one — a single hop can hide a bug the second one wouldn't), and
a new `B7` (Full Fleet Install/Update Confidence) added, mirroring how
Packager's own `P9` extended `P0`–`P8`'s single-app proof to all 5 real
apps. **A third revision, `B8` (Genuine Offline Confirmation), added
2026-08-21** after directly executing `B0`–`B2`: the original proposal's
`B6` was scoped for the genuinely air-gapped Validation VM, but the
revision moved every slice (including `B6`) onto `or-stt` (online) —
correct for proving Contract agreement, but it means the current plan
never actually re-proves a real Packager Release working through a
genuinely air-gapped Platform (each product alone was already proven
offline in Period A — `PL9b` for Platform with Golden Fixtures, the Real
Manual Acceptance Test for the Packager — but never the two together).
`B8` promotes that from an implicit footnote to a committed closing
slice: the same procedure already proven on `or-stt`, run once for real
on `Offline-AirGapped-Simulator`. Also settles two real questions with
live findings, not
assumptions: the Platform has no CLI and doesn't need one — for Period B
or for Period C's eventual Jenkins automation, since Jenkins drives REST
APIs directly and `PL1`'s own async operation pattern is already exactly
the shape CI/CD expects; and a real, working control channel already
exists — Platform is live right now on `or-stt`
(`172.26.121.111:8000`/`:8080`, confirmed via `docker ps`), its API is
directly reachable from the Legion with no SSH hop, and orchestration
should run from the Legion (matching this whole session's own proven
pattern), with the one necessary exception that a built Release must be
transferred to a **dedicated** release-storage directory on `or-stt`
(not the Golden Fixtures folder Platform's `RAH_RELEASE_STORAGE_PATH`
currently points at) before Platform can discover it at all. Recommended
first slice: **`B0` — Integration Harness & Traceability**. See
`docs/development/Period B — Cross-Product Integration/2. Initial
Slicing Task Table.md` for the full review and matrix.

**`B0` DONE, 2026-08-21.** Platform on `or-stt` now reads from a
dedicated `~/rah-platform-releases/` directory instead of the Golden
Fixtures folder (`docker-compose.override.yml`, local to `or-stt`,
untracked — live-confirmed via `health/ready` and an empty real scan;
every other container on the shared machine kept its original uptime,
untouched). A real `HCopilot_Release_1.0.3` was packaged on the Legion
(`overall_result: PASS`, fingerprint
`sha256:0097505413d24092750e57f92d27e137e909fbbdc0c799c80b22c6609389590e`)
and transferred to that directory over the existing `orstt_key` SSH
channel — fingerprint matched before and after transfer, and again after
a deliberate delete-and-retransfer (repeatability). One real finding,
root-caused and fixed: an independent `rah validate` against the
transferred copy first came back `FAIL` on two rules
(`RC-CFG-001`/`RC-SEC-003`, real-looking secrets in the config template)
despite `checksum_mismatches: []` — traced to `or-stt`'s cached
`rah-packager` image being 9 days stale (built 2026-08-11, predating a
placeholder-regex fix already present in that machine's own source
checkout), not a Packager bug or a real secret. Rebuilt the image on
`or-stt` from its current checkout; re-validated clean, all 56 rules
PASS/`NOT_APPLICABLE`. No installation, scan, or import performed yet —
deliberately `B1`/`B2`'s job. See
`docs/development/Period B — Cross-Product Integration/2. Initial
Slicing Task Table.md` for the full Testing Record and `B0-INT-001`.

**`B1` DONE, 2026-08-21.** No new code — `PL2`'s scanner was already
fully built in Period A; this slice proved it against real Packager
output. A real `POST /release-candidates/scan` on `or-stt` found
`HCopilot_Release_1.0.3` (left in place by `B0`) as `READY_FOR_IMPORT`,
identity matching exactly (`hcopilot`/`1.0.3`); repeated scanning
produced no duplicate; a deliberately partial second copy (checksums/
docker-images omitted) was correctly classified `INCOMPLETE` with the
precise reason while the real candidate stayed untouched; a live
`sha256sum` of the real candidate's `release.yaml` still matched `B0`'s
recorded fingerprint.

**`B2` DONE, 2026-08-21.** No new code — `PL3` already handled real
input correctly. Real import of `HCopilot_Release_1.0.3` succeeded,
creating application `hcopilot` for the first time; every manifest field
checked (`compose_project_name`, `canonical_path`, contract/schema
versions, `supported_operations`) matched the real `release.yaml`
exactly; fingerprint matched (cosmetic `sha256:` prefix difference only);
duplicate import was predictable (`already_imported: true`, no
duplicate row); a deliberately corrupted, genuinely new-identity test
candidate (`hcopilot@1.0.4`) was correctly rejected with real
`PLT-INTEGRITY-002` and exact per-file mismatches, no partial state
left behind. One real nuance recorded, not a confirmed defect: a
same-identity duplicate with a tampered *non-manifest* file short-
circuits on the "already imported" identity match without re-verifying
that specific directory — consistent with this project's own prior
decision that the Release fingerprint is deliberately `release.yaml`-only.
See the Period B task table for the full record. `B3` (Fresh
Installation) is next.

**`B2+` (urgent, unplanned fix) DONE, 2026-08-21.** Inserted between
`B2` and `B3` after `B3`'s first real attempt (installing a real,
re-packaged `HCopilot_Release_1.0.4`) failed with `cp: X and X are the
same file` inside the real install script. Root cause: Platform's
`PL6`-era staging copied a Release's entire payload into the live
canonical deployment path and ran scripts from that copy, collapsing
the Release's own immutable location (`RELEASE_DIR`) and the permanent
live deployment directory (`canonical_path`) into the literal same
directory — real Applications' own scripts (correctly) assume these are
two different places and copy content between them, which self-
collides when they're not. Fixed properly, not patched around: lifecycle
scripts now run in place from `release_storage_path` (matching
`backup.py`/`recovery.py`'s pre-existing, already-correct convention),
with the live path passed explicitly via `RAH_ACTIVE_DEPLOYMENT_PATH`;
15 Golden Fixture scripts and their checksums updated to stop relying on
Compose's implicit `.env` lookup. **No real Application needed any
change** — HCopilot's (and every other real app's) own scripts already
hardcode their live path as `/opt/rah/apps/<slug>`, already matching
Platform's own `deployments_path` default; only Platform's staging
shortcut had broken the agreement the two products already shared. Full
Platform test suite reconfirmed clean on `or-stt` against real
Postgres/Docker: 167 passed, 0 failed. One test-harness gap found and
fixed along the way (a test bypassing the real install path had never
rendered a config file at all, silently tolerated before this fix and
correctly surfaced by it). See the Period B task table's own `B2+`
section for the full record. `B3` (retry, now against a Platform whose
real behavior matches the documented architecture) is next.

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
   **DONE**. Both tracks' own Period A Exit Gates are satisfied for real,
   not assumed:
   - **Packager**: `P0`–`P7` (automated portion) built and tested, `P8`
     (Model Artifacts & Offline-Completeness Closure) done, then **the
     Real Manual Acceptance Test passed end-to-end, 2026-08-20** — Attempt
     1 (2026-08-11) FAILED at Phase 1 on an Indicator-repo defect
     (non-executable lifecycle scripts), now fixed; a later attempt passed
     all six phases for real against real lab hardware (`or-stt`,
     `Offline-AirGapped-Simulator`). Three real bugs found and fixed
     getting there, one serious (a Packager image-export bug affecting
     every prior Release). **`P9` (Full Fleet Validation) then confirmed
     all 5 real apps** (HCopilot, Indicator, STT-SCHEDULE, Voice Project,
     HCAT) pass `rah package` for real. See
     `docs/development/Period A — Independent Product Development;
     Packager/2. Initial Slicing Task Table.md` and
     `.../3. Real Manual Acceptance Test — Results.md`.
   - **Platform**: `PL0`–`PL9b` all done and tested — the full 23-step
     Offline Acceptance Scenario ran for real on the genuinely air-gapped
     Offline Validation VM, found and fixed a real `RECOVER`-availability
     gap live. See
     `docs/development/Period A — Independent Product Development;
     Platform/2. Initial Slicing Task Table.md`.

   Two loose Packager-track ends remain open, neither part of either Exit
   Gate: the Playbook §11a/§7a mirror-sync, and merging the STT-SCHEDULE
   `offline-deployment` branch (paused on real conflicts with `master`'s
   own in-progress work).
7. Begin Period B (Cross-Product Integration) — **READY TO START, not yet
   begun**. Both Period A tracks' Minimum Gates (defined in
   `docs/development/Period B — Cross-Product Integration/1. Initial GPT
   Proposal.md`, lines 43–79) are met, which is Period B's own explicit
   Entry Gate — it does not start merely because development has
   progressed far enough. Recommended first slice: `B0` (Integration
   Harness & Traceability) — see "Period B — Integration" above.

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

**Nothing structural — the Real Manual Acceptance Test is fully PASSED
for the first time (see above).** What's left is sequencing, not
discovery: (1) commit and push the Packager fixes from this session
(fingerprint self-invalidation loop, sibling-script copy gap, the
image-tag export bug — the last one is serious and affects every prior
Release) so they exist anywhere other than this machine; (2) push
Indicator's own script fixes (committed locally, not yet pushed); (3)
decide on the three unmerged `bake-whisper-model`/`offline-deployment`
branches (Voice Project, HCAT, STT-SCHEDULE) per the branching policy —
merge only once `P9` confirms each fix end-to-end; (4) re-verify
HCopilot's P8 proof against the newly-discovered image-tag bug — it was
never actually load-tested on a separate Docker Engine; (5) `P9`: retest
all 5 real apps and record results. See the short task list in
`docs/development/Period A — Independent Product Development;
Packager/2. Initial Slicing Task Table.md` for the concrete sequence.

## Next Major Gate

**Achieved, 20/08/2026**: the Real Manual Acceptance Test, Phases 1–6,
passed end-to-end for the first time — Indicator packaged for real,
transferred to `Offline-AirGapped-Simulator` over the internal switch,
independently re-validated with zero checksum mismatches, installed via
its own `install_offline.sh`, verified healthy, and confirmed to survive
a real stop/start restart cycle unattended. This is the last piece of the
Period A Packager Exit Gate ("a real application can be initialized,
inspected, assisted through Claude, planned, built, packaged, validated,
finalized, manually installed offline, and a second Release can be
produced without corrupting version history") — now demonstrated for
real, not assumed. **Next gate**: `P9` — the same proof across all 5 real
apps, plus the two documentation gaps already tracked there.

## Future Design Tasks (not yet started)

- **Packager operational error-code namespace** (e.g. `PKG-*`, distinct
  from the Contract's `RC-*` validation-rule namespace) — covering Git
  inspection, Docker discovery, Claude interaction, configuration, and
  runtime failures. Full namespace design (numbered sub-codes, a complete
  category list, etc.) is still deliberately not started. See
  `docs/development/Period A — Independent Product Development;
  Packager/1. Initial GPT Proposal.md` (P5, where `PKG-DOCKER-*` is
  referenced as if it already exists).

  **Partial reconciliation done** (before starting the Real Manual
  Acceptance Test): of the four concrete gaps this bullet used to list,
  two were category-naming outliers that were fixed outright, narrowly
  scoped to just those two — no broader namespace redesign attempted:
  - `DockerUnavailableError`: `PKG-RUNTIME-DOCKER-UNAVAILABLE` →
    `PKG-DOCKER-UNAVAILABLE` (`RUNTIME` was never one of the architecture's
    11 named categories; `DOCKER` already existed and fits).
  - The three P6 manifest/model errors: `PKG-RELEASE-MANIFEST-SCHEMA-INVALID`
    → `PKG-MANIFEST-SCHEMA-INVALID`, `PKG-RELEASE-MANIFEST-INCOMPLETE` →
    `PKG-MANIFEST-INCOMPLETE`, `PKG-RELEASE-MODELS-NOT-SUPPORTED` →
    `PKG-MANIFEST-MODELS-NOT-SUPPORTED` (folded into the architecture's own
    named `PKG-MANIFEST` category instead of the ad hoc `PKG-RELEASE-*`
    prefix). `errors.py`, `cli.py`-adjacent tests (`test_cli.py`,
    `test_health.py`, `test_release_manifest.py`), and the one source
    comment in `construct_release.py` referencing the old string were all
    updated together; 169/169 tests still pass.

  **New finding surfaced while doing that reconciliation, deliberately
  NOT fixed this pass** (scoped narrowly to the two items above, per
  explicit instruction — recording it so it doesn't silently vanish the
  way the first two outliers almost did): auditing every implemented code's
  category segment against the real 11-category list turned up two more
  non-conforming groups that were never on this list before —
  `PlanProjectNotInitializedError`/`PlanDirtySourceError`/
  `PlanDuplicateVersionError` (`PKG-PLAN-*`) and
  `ReleaseNotFoundError`/`ReleaseComplianceFailedError`/
  `ReleaseAlreadyExistsError`/`ComplianceReportSchemaError`
  (`PKG-RELEASE-*`/`PKG-COMPLIANCE-*`). None of `PLAN`, `RELEASE`, or
  `COMPLIANCE` is one of the architecture's 11 named categories either.
  These are real candidates for the eventual full namespace design
  discussion (`ReleaseComplianceFailedError` in particular looks like it
  should be `PKG-CONTRACT-*`, since RC-* rule failure is literally what
  exit code `7`, "Release Contract validation failure," means) — left
  alone here rather than guessed at mid-cleanup.

  **Decision on the other two original items — richer error shape and
  differentiated exit codes — deferred for V1, not implemented**, for a
  reason that only became clear from the finding above: `PackagerError.to_dict()`
  still only emits `{code, message}` (not the architecture §9 7-field shape:
  `category`/`stage`/`details`/`retryable`/`log_reference`), and §8's
  CLI exit-code table (`2`–`10`) is still not wired into `cli.py` (every
  command still exits `1` on any `PackagerError`). Building either one now
  would require a `code → category`/`code → exit-code` lookup, and that
  lookup can't be built soundly yet — the namespace is still only
  partially reconciled (`PLAN`/`RELEASE`/`COMPLIANCE` remain unmapped, per
  above), so shipping the lookup now means either solving the full
  namespace design task immediately (explicitly out of scope for this
  pass) or shipping mappings already known to be wrong for several error
  classes. Neither is better than waiting. `log_reference` separately
  assumes a per-operation log-file feature that doesn't exist yet
  (logging is stderr-only). No downstream consumer needs any of these five
  fields yet, so nothing is blocked by deferring. Revisit this whole bullet
  together, as one pass, once/if the namespace is actually designed —
  piecemeal fixes are what created the `PLAN`/`RELEASE`/`COMPLIANCE` gap in
  the first place.

- **Period C must inherit the mocked-vs-live testing discipline already
  proven in `P3`, not silently drop it.** `packager/tests/test_claude_client.py`
  mocks the real `anthropic.Anthropic` client via `monkeypatch` for every
  automated test — real Anthropic API spend only happened once,
  deliberately, for the actual `rah prepare-answers` live-proof (~$0.54
  total). That split is what keeps the automated suite fast, free, and
  deterministic while still getting a genuine live proof once. When
  Jenkins automates this pipeline, someone has to make sure the CI
  pipeline keeps that same split — mocked in the routine automated run,
  real API calls only where a genuine live-proof gate actually requires
  it. If that boundary gets blurred during automation, a trivial
  one-time cost becomes a recurring per-build cost instead, and the
  suite may also become flaky (network/rate-limit dependent) where it
  currently isn't. Not a problem today — `docs/development/Period C —
  Jenkins Automation/1. Initial GPT Proposal.md` is still empty, Period C
  hasn't started. Worth a checklist item once it does.

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
