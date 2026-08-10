# Release Contract V1 — Completion Log

This is the review artifact for the "Executable Release Contract V1" phase
gate described in `docs/development/CURRENT.md`:

> Materialize Release Contract V1 → **review every COMPLETED decision** →
> only after review, declare Contract V1 FROZEN.

The four files in `contracts/1.0/` are **materialized, not frozen**. This
document is what gets reviewed before that freeze happens.

## Taxonomy

- **EXTRACTED** — taken directly from explicit architecture prose. Low
  review burden; the judgment call was already made when the architecture
  was written.
- **COMPLETED** — the architecture left a gap, was silent, or only
  described a category without enumerating it fully. Filled here using
  engineering judgment, grounded wherever possible in real evidence (HCAT's
  and Voice Project's actual `release/` folders). **These are what need
  your review** — not because they're wrong, but because they're new
  decisions, not restatements of an existing one.
- **ARCHITECTURE CONFLICT** — something that cannot satisfy the frozen
  architecture's explicit text as written. **None found.** Every gap
  encountered was silence (the architecture not addressing something), not
  contradiction (the architecture saying one thing and the Contract doing
  another). This is a genuinely good sign for how coherent Stage 4 already
  was — worth knowing on its own, not just as a preface to the list below.

## COMPLETED decisions requiring your review

### 1. Model artifacts no longer reference a packaged file path

The architecture's Manifest `models` section (`4. Stage 4...md` §23)
assumed each model artifact declares a `packaged_path` — a file sitting
somewhere in the Release tree. This project later decided (mid-conversation,
recorded in `docs/decisions/packager-responsibility-boundaries.md`) that
all app-specific binary content, ML models included, bakes into a Docker
image instead. `release-manifest.schema.json#/properties/models` therefore
replaces `packaged_path` with `baked_into_image` (names the
`docker.images[].service` the model lives inside) and keeps `checksum` as
provenance computed by the Packaging Engine before the Docker build, not a
value re-verified by extracting the image later.

**Why this is probably right, not just convenient:** matches the real,
working precedent already observed — HCAT's small classification models
are already baked into `backend.tar` via a plain `COPY` in
`backend/Dockerfile`, and the byte-identical Whisper zip duplicated across
`release/0.1.0/` and `release/0.1.1/` proved the old "separate asset"
approach wasn't even saving transfer size.

### 2. No `assets/` (or `models/`) top-level Release directory

Direct consequence of #1. `release-layout.yaml` has no `assets/` entry.
Confirmed by grep that the architecture never assumed one existed either
(zero matches for "assets/" as a directory concept across all five
architecture documents searched).

### 3. `validation-rules.json`'s file shape is new

No standalone `validation-rules.json` structure was ever drafted in the
architecture — only ~40 example rules in prose plus category obligation
lists. The `{id, category, provenance, mandatory, description,
architecture_reference, validation_stage}` shape, and the `RC-CON` /
`RC-OFF` categories specifically (named as categories in the architecture
but never given example rule IDs), are new constructions. 57 rules total;
every rule's `architecture_reference` field points at the specific prose
this project traced it back to.

### 4. Every rule is currently marked `mandatory: true`

The architecture names the concept of a "warning" rule that doesn't affect
overall compliance (`4. Stage 4...md` §9.20) but never identifies which
specific rule, if any, should be warning-level rather than mandatory. This
Contract version treats all 57 rules as mandatory. Revisit if a real need
for a non-mandatory rule shows up during Packager implementation.

### 5. `release_identity` object in the Compliance Report

The architecture requires the report to include "Release identity"
(§9.21) but never enumerates its sub-fields. `{application_slug, version,
release_fingerprint}` was chosen to match the identity fields used
elsewhere in the Contract and the `PackagingResult`'s "Release fingerprint"
field (`4.6...md` §6.6).

### 6. `rules_not_applicable` / `rules_not_executed` counters added to the summary

The architecture's minimum stats list (§7.9) only requires
executed/passed/failed. `NOT_APPLICABLE` and `NOT_EXECUTED` are real,
separately-defined outcome states elsewhere in the same architecture
(§9.8), and §9.21 requires the report to include explanations for both —
counting them in the summary follows directly from that, but the summary
object's exact shape is a completion, not a restatement.

### 7. JSON Schema draft version

`http://json-schema.org/draft-07/schema#` for both schema files — a
tooling choice with no architecture opinion either way. Chosen for broad
validator compatibility over the newer 2020-12 draft; revisit if the
eventual Packager implementation language has a strong preference.

### 8. Manifest schema validates structure/type only, not cross-field semantics

Deliberately incomplete by design, not an oversight: the architecture's
own Validator sequence (`4. Stage 4...md` §9.5) treats "manifest schema
validation" and "cross-field identity/semantic validation" as two separate
steps. `release-manifest.schema.json` handles the first; `RC-MAN-004`
through `RC-MAN-006`, `RC-SCR-004`, and others in `validation-rules.json`
handle the second. If a future session tries to "complete" the JSON Schema
by adding `if/then` conditionals for things like "install entrypoint
required when fresh_install is true," check this log first — that's
intentional separation, not a gap.

### 9. `RC-REPRO-001` — reproducibility promoted from the Packager plan to the Contract

The Packager development plan's own P6 "Reproducibility" test already
contained a workable definition — "same known input should produce
structurally equivalent candidate Release, except fields deliberately
expected to vary" — that the frozen architecture itself never reached
(§11.1 names reproducibility as a goal but never operationalizes it).
Promoted into `validation-rules.json` as `RC-REPRO-001`, with an explicit
note that it's the one rule category requiring two independently built
candidate Releases to compare, not a step in the normal single-Release
validator sequence — see `validation_order_note` in the file itself. A
known limitation is recorded alongside it, not asserted as a rule: Docker
image archive content equality isn't guaranteed, since that depends on
whether the underlying `docker build` process is itself reproducible.
`compliance-report.schema.json`'s rule-id pattern was also corrected in
the same pass — it required exactly 3 letters after `RC-`, which would
have rejected legitimate `RC-DB-*` ids (2 letters) even before
`RC-REPRO-*` (5 letters) made the bug unmissable. Now `^RC-[A-Z]{2,6}-[0-9]{3}$`.

## Cross-checked against real evidence

`HCAT` (`Patient_Feedback/release/`) and `Voice Project`
(`voice-project_Deployment/release/0.1.0/` and `0.1.1/`) are real,
hand-built precursors that heavily informed this Contract's shape — but
they predate it, and are **not** expected to already satisfy it as-is.
Three concrete gaps found, worth knowing rather than being surprised by
later:

1. **Neither real release folder has a `release.yaml` manifest at all.**
   Expected — nothing has produced one yet; that's what Packager slice P6
   (Release Construction) adds. Not a Contract problem.
2. **Neither has a `compliance/` directory or Compliance Report.**
   Expected — nothing has run a Validator against them yet; that's
   Packager slice P7. Not a Contract problem.
3. **The checksum file is named `release_hashes.txt`, not
   `checksums/SHA256SUMS`.** This one *is* a real naming difference
   between existing informal practice and the Contract's requirement
   (`checksums/SHA256SUMS` is EXTRACTED directly from architecture prose,
   not invented). Not changing the Contract to match the old name — when
   the real Packaging Engine eventually runs against these apps, it
   produces a new, Contract-compliant Release directory per the
   additive-versioning rule; it doesn't need to retrofit the old one.
4. **HCAT's existing `release/assets/whisper-model-medium.zip` still
   exists**, which is the old, pre-decision shape (decision #1/#2 above
   postdate it). Same resolution as #3 — the next real Packager run
   produces a fresh, compliant Release; the old folder isn't edited in
   place.

None of these four are Contract defects. They're the expected gap between
"a Contract that formalizes a proven pattern" and "hand-built folders that
predate the Contract and the Packager that will eventually produce its
compliant successor."

## Recommendation

Nothing above rises to the level of a re-architecture — every COMPLETED
item is a narrow, traceable, cited extension of something the architecture
already named but didn't finish enumerating. My recommendation: review
items 1, 4, and 9 above most carefully (they're the ones closest to being
actual design choices rather than mechanical completions — item 9 in
particular resolves what was, until the Packager plan review, the one
genuinely open design question in this Contract: reproducibility had no
checkable rule at all), skim the rest, and freeze.
