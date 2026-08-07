---
name: voice-project-release-validation
description: "Voice Project (Blood Bank transcription app) offline release architecture, where its release packages live, and status of its install/update validation experiment"
metadata: 
  node_type: memory
  type: project
  originSessionId: 0b86e611-a462-4758-9ca5-adfeee53440d
---

**Voice Project** = a Blood Bank voice-transcription system (`zeinabelsamra/voice-project`
upstream, deployed via a separate `voice-project_Deployment` repo). Release packages live
on the Legion at `C:\Users\it\Documents\GitHub\voice-project_Deployment\release\{0.1.0,0.1.1}`
— this is a different application from RAH-OIP itself; see [[rah-oip-lab-topology]] for the
shared lab infrastructure both are tested on.

**Real architecture differs from the generic "Experiment 1" validation-plan doc that was
written for it** — the plan doc assumes PostgreSQL/Alembic; the actual stack is:
- Database: **SQL Server** (`mcr.microsoft.com/mssql/server:2022-latest`), migrations are
  numbered `.sql` scripts under `database/sqlserver/install/` run via `sqlcmd`, with a
  recorded schema-version marker — not Alembic.
- Services: `sqlserver`, `db-init` (one-shot installer), `whisper` (speech-to-text, not
  mentioned in the plan doc at all), `backend` (node — serves API **and** the static
  frontend, no separate frontend image), `nginx` (stock `nginx:1.27-alpine`, TLS-terminating
  reverse proxy only, ports 80/443).
- Release-folder version and baked image tag differ by a fixed offset: release `0.1.0` ↔
  image tag `1.0.0`, release `0.1.1` ↔ image tag `1.1.0` (`IMAGE_VERSION` in compose).
- Default login after fresh install: `admin`/`admin123` (must be changed immediately per
  `VALIDATION_CHECKLIST.md`).
- RELEASE_NOTES.md for 1.1.0 explicitly says it had only been tested as an **update** over
  a running 1.0.0 before this project's Scenario A run — fresh-installing 0.1.1 standalone
  was previously unverified territory.

**Why this matters:** when working from the "Experiment 1" plan doc, translate its
PostgreSQL-specific language to the real SQL Server tooling rather than treating the doc
as literal instructions — confirmed correct approach with the user 2026-07-16.

**Status as of 2026-07-27:** Two deployment-fork fixes landed on top of the 2026-07-16
release/0.1.1 baseline (repo now 5 commits ahead of `origin/main`, unpushed):
1. **Nginx WebSocket fix** (commit `9c0977c2`, 2026-07-16) — chat's Socket.IO handshake
   was silently downgraded to plain HTTP because `nginx.conf` didn't forward
   `Upgrade`/`Connection` headers. Config-only fix, no image rebuild needed.
2. **CDN removal** (uncommitted as of 2026-07-27, made 2026-07-22) — `frontend/index.html`
   previously pulled Google Fonts from `fonts.googleapis.com` and Chart.js from
   `cdn.jsdelivr.net`, which would silently fail on the real air-gapped hospital server
   (no internet). Now vendored: fonts self-hosted at `frontend/fonts/*.woff2` +
   `fonts.css`, Chart.js at `frontend/vendor/chart.umd.min.js`. Also dropped a dead
   jsPDF CDN `<script>` tag (PDF export already goes through backend `pdfkit`).
   `voice-project-backend:1.1.0` rebuilt and `backend.tar` re-exported to bake this in.

**Re-ran Test Scenario A (fresh install of 0.1.1) on 2026-07-27 against current
release/0.1.1 (including both fixes above) — PASSED.** Offline VM was reverted to
`GoldenSnapshot-WithRAHOIP` first (wipes prior unrelated STT-SCHEDULE test state — see
[[stt-schedule-release-validation]] — evidence from earlier runs does not survive a
snapshot revert, so don't expect old `~/experiment-01-update-validation/` paths to still
exist after one). Confirmed on the genuinely air-gapped VM: all 4 containers healthy, DB
validation passed, `curl https://example.com` → connection failure (true no-internet),
served `index.html` has zero `fonts.googleapis.com`/`cdn.jsdelivr.net`/
`cdnjs.cloudflare.com` references, `fonts/fonts.css` + `vendor/chart.umd.min.js` +
a sample `.woff2` all serve 200 from nginx itself, `/socket.io/` polling handshake
returns 200, and the `map $http_upgrade $connection_upgrade` WebSocket block is live
inside the running `voice-project-nginx-1` container. Did not get a browser-rendered
screenshot (no GPU/X server for headless Firefox on that VM) — verification is via curl
+ container inspection, not visual confirmation, but that directly proves the underlying
bug (CDN dependency) is gone.

**Still not yet re-run:** Scenarios B–E (install 0.1.0 with test data, update to 0.1.1,
idempotency, rollback). Also: the CDN-removal and WebSocket-fix changes are still
uncommitted/unpushed on the Legion (`frontend/index.html`,
`release/0.1.1/checksums/release_hashes.txt` modified; `frontend/fonts/`,
`frontend/vendor/` untracked) — commit them once satisfied.
