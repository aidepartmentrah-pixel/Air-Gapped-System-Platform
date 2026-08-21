# Packager Readiness — Internal Reference

A working dashboard of where each of the 5 real applications actually
stands with respect to the shared RAH Packager + Platform pipeline —
built for `B6`/`B7` (Full Fleet Install/Update Confidence), so those
slices don't have to rediscover this from scratch. Kept up to date as
each app is actually investigated or tested — don't assume a row is
still accurate without re-checking if a lot of time has passed.

Last verified: 2026-08-21, alongside `B3`.

## Status Table

| Application | Uses the shared RAH Packager? | Real Platform install verified? | Known blockers | Fleet-slice readiness |
|---|---|---|---|---|
| **HCopilot** | ✅ Yes (has `.rah/`) | ✅ Yes — `B3` DONE, real install `SUCCEEDED` (`HCopilot_Release_1.0.7`) | `database/*.sql` never actually packaged — breaks backup/restore specifically, not install (see `bugs-faced.md` #5) | Install: ready. Update/Backup (`B5`): **blocked** until the `.sql` packaging gap is fixed |
| **Healthcare_reporting_system_backup** | ✅ Yes (has `.rah/`) | ❌ Not yet tested via Platform this session | Unknown — its own `install_offline.sh` already reads the config template from the correct `configuration/` path (unlike HCopilot's original bug), but that's the only thing checked; never run through a real install | Needs its own real `B3`-equivalent test before counting on it — don't assume it "just works" because one script line was correct |
| **STT-SCHEDULE** | ❌ No — its own `scripts/build_release_images.sh`, no `.rah/` | N/A (doesn't produce a Packager-built Release) | Would need migration onto the shared Packager, or Platform would need a way to install non-Packager-built Releases (it doesn't) | **Not currently packageable through this pipeline at all** |
| **RESTful-API-Integration** | ❌ No — its own `scripts/build_release.sh`, no `.rah/` | N/A | Its `install_offline.sh` doesn't auto-configure at all — it expects an operator to manually `cp .env.offline.template .env` and hand-edit secrets before running, which is fundamentally incompatible with Platform's automated install model regardless of packaging | **Not currently packageable/automatable** — a bigger gap than a script bug |
| **HCAT (`Patient_Feedback`)** | ❌ No — custom `release-manifest.json` build, not the Release Contract's `release.yaml` schema at all | N/A | Entirely different manifest schema; previously flagged as deferred ("multi-model complexity") before this session even started | **Not currently packageable through this pipeline** — would need real Release Engineering work, not just a script fix |
| **Voice Project (`voice-project_Deployment`)** | ❌ No — no `.rah/`, no dedicated build script found this session | N/A | Previously flagged, separate, more severe issue: manual `.env` pre-population baked into the release package (deferred, not re-investigated this session) | **Not currently packageable/automatable** |
| **Indicator** | ❓ Unknown | ❓ Unknown | Repo not present in any working directory accessible this session — genuinely not checked, not "assumed fine" | **Unverified** — needs its own investigation before `B6`/`B7` can rely on anything about it |

## What this means for `B6`/`B7`

- **Only HCopilot is currently proven** to work through the real, shared,
  automated Packager → Platform pipeline for a fresh install — and even
  that one still has an open backup/restore gap.
- **Four of the five apps in the original fleet don't use the shared
  Packager at all** — `B7`'s "3 real Releases per app, all 5 apps" scope
  needs a real decision before it can proceed as originally scoped: either
  those apps get migrated onto the shared Packager first (real work, not
  a quick fix), or `B7`'s own scope gets revised to reflect which apps are
  actually reachable through this pipeline today.
- This table is the answer to "which ones are actually ready" — check it
  before assuming any app beyond HCopilot will behave, and update it as
  each one gets its own real investigation.
