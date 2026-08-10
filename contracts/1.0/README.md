# RAH Application Release Contract — Version 1.0

Status: **FROZEN** — user-confirmed. See
`docs/development/contract-v1-completion-log.md` for the full review
trail (zero ARCHITECTURE CONFLICT items). Any future edit is a deliberate,
separate decision, not a reopening of this review.

## What's here

| File | Purpose |
|---|---|
| `release-layout.yaml` | The required on-disk shape of an Application Release — directories, files, naming convention, path rules. |
| `release-manifest.schema.json` | JSON Schema for `release.yaml`, the single authoritative Release Manifest every Release carries. Structural/type validation only — see the schema's own description for why. |
| `validation-rules.json` | The full catalog of rules (`RC-*`) a Release Validator checks before declaring a Release `COMPLIANT`, including cross-field/semantic rules the Manifest schema deliberately does not encode. |
| `compliance-report.schema.json` | JSON Schema for the generated, immutable `compliance/release-compliance-report.json` every successfully-validated Release carries. |

These four files were materialized from the frozen prose architecture in
`docs/architecture/` (primarily `4. Stage 4 — Choose Implementation
Mechanisms.md`, plus `4.6`/`4.7` for the Packaging Engine and Offline
Platform specifications). Where the architecture was silent or left a gap,
a judgment call was made and recorded — see the completion log for the
full list, tagged `EXTRACTED` (directly from architecture prose) or
`COMPLETED` (a gap filled here, flagged for review).

## Two decisions this Contract version bakes in

Both made explicitly during Contract materialization, both consistent with
the frozen architecture but not literally spelled out in it:

1. **No separate `assets/` (or `models/`) directory.** All
   application-specific binary content, including ML models, is baked
   into a Docker image via ordinary `COPY` rather than shipped as a
   separately-extracted Release asset. See
   `docs/decisions/packager-responsibility-boundaries.md`.
2. **Release versions are additive, never overwritten.** Every `rah
   package` run produces a new, immutable, versioned Release directory.
   Confirmed both by explicit architecture statements (state-safety rules,
   append-only `release_history`, Manifest/Compliance-Report immutability)
   and by real evidence (`release/0.1.0/` and `release/0.1.1/` coexisting
   in `voice-project_Deployment`'s actual repo).

## How this Contract version evolves

(EXTRACTED — `4. Stage 4...md` Chapter 11, "Contract Evolution.")

- **Format**: `MAJOR.MINOR` only — no patch component. Implementation bug
  fixes belong to Generator/Validator versions, not the Contract, as long
  as the Contract's own meaning is unchanged.
- **MAJOR** (`1.x → 2.0`): any change that could make an existing
  compliant Release incompatible — removing a field, changing a field's
  meaning, renaming a mandatory directory, changing mandatory script
  interfaces, making a previously-optional artifact mandatory, or changing
  what an existing validation rule means.
- **MINOR** (`1.0 → 1.1`): backward-compatible additions only — optional
  fields, optional artifact categories, new validation rules for newly
  introduced optional behavior. A Contract 1.1 Platform should continue
  supporting valid Contract 1.0 Releases.
- **Errata**: wording/clarification fixes that don't change normative
  meaning — no version bump. If a correction would change a pass/fail
  outcome, it's not errata — it requires a version bump instead.
- A Release is validated according to the Contract version it explicitly
  declares (`compatibility.release_contract_version`), permanently. Future
  Contract versions never retroactively redefine whether an already-frozen
  Release was compliant.
- **Current scope**: only Contract `1.0` is supported. Additional versions
  get introduced only when an actual compatibility or evolution need
  arises — this is a designed extension point, not yet exercised.
