# Engineering Answers Schema and Staleness — A Design the Architecture Left Open

Unlike the Project Version State (P1), the frozen architecture never drafted
a schema for `.rah/engineering-answers.json`. The proposal document says so
directly: staleness was flagged as *"one of the weaker areas identified
during architecture review."* This document is that missing design,
written from real evidence — the frozen Release Manifest schema — rather
than invented from scratch. Implementation:
`packager/src/rah_packager/engineering_answers.py`.

## The schema is the gap, not a parallel invention

`ENGINEERING_ANSWERS_SCHEMA` was derived by diffing `contracts/1.0/release-manifest.schema.json`
(frozen, tested, real) against what P2's `ProjectInspectionResult` already
determines deterministically. Whatever's left over — genuine engineering
judgment calls a repository scan can't answer — is what the schema asks
for. Concretely:

- **Excluded entirely**: `application.{name,slug}`, `release.*`,
  `source.*`, `docker.*`, `integrity` — either P2 already knows these
  (git commit, compose file, service names) or they're generated later
  (release version, timestamps, checksums). Asking Claude to re-derive
  something P2 already knows deterministically would be redundant and a
  real source of contradiction between "what P2 found" and "what Claude
  said" — better to never ask the question at all.
- **Structurally identical to the manifest**: `compatibility`,
  `configuration.inputs[]`, `database`, `persistent_state`,
  `offline_requirements`, `client`, `verification` — these sections exist
  in engineering-answers.json *because* they're copied straight into the
  eventual manifest. Reusing the manifest's own field names, enums, and
  structure isn't a style choice, it's the actual contract: whatever
  Claude answers here is what P6 (Release Construction, not built yet)
  will read back out unchanged.
- **Trimmed from the manifest's shape**: `models.artifacts[]` drops
  `baked_into_image` and `checksum` — both are computed at packaging time
  from the actual Docker build, not answerable during engineering.
  `deployment` drops `canonical_path` — that's `/opt/rah/apps/<slug>`,
  computed from the slug P1 already assigned, never a question.
- **New, because P3 needs it and nothing else does**: `application.description`,
  and the `based_on` staleness anchor (below).

## Same structural/semantic split the manifest itself already uses

The manifest schema's own description says it plainly: *"Cross-field,
conditional, and semantic rules... are deliberately NOT encoded here...
Those rules live in validation-rules.json instead."* `ENGINEERING_ANSWERS_SCHEMA`
follows the identical split — it validates shape and types only.
Cross-field rules (e.g. "if `database.required` is `true`, `platform`
must be present," or "every `configuration.inputs[].key` must match a
name P2 actually discovered") are deliberately **not** encoded in the
schema. They're application-level checks that belong to `rah
validate-answers`, the same way the Contract's own semantic rules live in
`validation-rules.json`, a separate file from the manifest's structural
schema.

## Three-tier questions, not a blank form

`rah prepare-answers` (not built yet) isn't meant to hand Claude an empty
form. Every field in the schema falls into one of three tiers, and the
tier determines what `prepare-answers` puts in the request:

1. **Pre-seeded from P2, needs confirmation** — e.g. `deployment.entrypoints`
   guessed from `application_resources.scripts` filenames
   (`install_offline.sh` → `install`), `documentation.*` guessed from
   `application_resources.documentation` filenames (`INSTALL_OFFLINE.md`
   → `installation`), `database.platform` hinted from a Compose service's
   image name (`mcr.microsoft.com/mssql/server` → `sqlserver`).
2. **Pre-seeded from the Contract's own stated norm, needs confirmation**
   — `offline_requirements.*` defaults to `false` ("shall normally all be
   false"), `models.required` defaults to `false` absent any discovered
   model artifact, `client.*` defaults to `false` absent any HTTPS-suggestive
   signal.
3. **Genuinely open** — `application.description`,
   `compatibility.minimum_rah_oip_version`,
   `compatibility.required_shared_services`,
   `deployment.supported_operations`/`transition`,
   `persistent_state.preserve_during_update`. Nothing to suggest; real
   judgment.

## Staleness: two anchors, not one

`based_on` records two things at `prepare-answers` time:

- `git_commit` — cheap, human-readable, catches "the repo moved to a new
  commit."
- `inspection_fingerprint` — `compute_inspection_fingerprint()`, a sha256
  of the full canonicalized `ProjectInspectionResult` (deterministic
  regardless of key order — `json.dumps(..., sort_keys=True)`). This
  catches everything `git_commit` alone would miss: a working tree that
  went from clean to dirty without a new commit, a Dockerfile added, a
  script renamed, `docker-compose.yml` edited before committing. Since P2
  already reports Git's clean/dirty state as one of its own fields, an
  uncommitted change to a *discovered* fact changes the fingerprint even
  when `git_commit` hasn't moved.

`rah validate-answers` (not built yet) recomputes both against the
*current* repo — not the state at `prepare-answers` time — and treats any
mismatch as staleness. This satisfies the spec's explicit required test
("answers generated against old Git commit detected as stale") and goes
further than a naive commit-only check would.

## What's still open

This document covers the schema and the staleness mechanism. It does not
yet cover: the exact prompt/context bundling strategy for `prepare-answers`
(what file contents get sent to Claude alongside the discovered facts —
see the conversation record for the three-tier design above), or the
`rah validate-answers` cross-field rule set itself (analogous to
`validation-rules.json`, not yet written). Both are separate, later
implementation steps against this frozen schema, not open schema
questions.
