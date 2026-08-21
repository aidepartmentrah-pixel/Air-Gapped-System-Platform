# Bugs Faced — Real, Live-Found Defects

A running log of real bugs found through actual execution (not theory) during
cross-product integration testing — who was at fault, the root cause, the
fix, and current status. Kept separate from `CURRENT.md`'s narrative history
so the full list stays scannable in one place. Append new entries; don't
rewrite old ones once fixed.

Convention per entry: **What broke** → **Root cause** → **At fault** →
**Fix** → **Status**.

---

## 2026-08-21 — Period B, `B3` (Fresh Installation) retries

### 1. Platform: double `scripts/` path prefix

**What broke:** Install/update script resolution built a path like
`.../scripts/scripts/install_offline.sh` — one `scripts/` too many.

**Root cause:** `installation.py`/`update.py` joined `canonical_path` +
`"scripts"` + `entrypoint`, but the manifest's declared `entrypoint` value
(e.g. `scripts/install_offline.sh`) already includes the `scripts/` prefix
— a full path relative to the Release root, not a bare filename.

**At fault:** Platform.

**Fix:** Removed the extra `"scripts"` segment in both files (and confirmed
`backup.py`/`recovery.py` never had this bug). 19 Golden Fixtures had the
same wrong assumption baked into their declared entrypoints; bulk-fixed to
full paths, checksums/compliance reports recomputed.

**Status:** ✅ Fixed (commit `07c1787`).

---

### 2. HCopilot: "already installed" check used rendered-config presence

**What broke:** A fresh install via Platform was rejected as "already
installed" even though nothing had ever been installed.

**Root cause:** `install_offline.sh` used the mere existence of the
rendered production `.env` as its "already installed" signal. Platform
legitimately renders that file as a preparation step immediately before
*every* install (not just updates) — so the file's presence proves nothing
about whether a previous install ever completed.

**At fault:** HCopilot (application-specific — the script's own
idempotency check was checking the wrong thing).

**Fix:** Switched the check to a dedicated completion marker
(`INSTALLED_VERSION`, written only at the end of a fully successful
install/update) instead of config-file presence.

**Status:** ✅ Fixed (HCopilot commit `519d99c`). Documented in the Playbook
as **§22a** (added 2026-08-21, having been drafted earlier but never
actually written into the tracked file until this session).

---

### 3. Platform: `RELEASE_DIR` and `canonical_path` were the same directory

**What broke:** A real install failed with `cp: X and X are the same
file` inside HCopilot's own install script.

**Root cause:** Platform's staging model copied a Release's entire payload
into the live canonical deployment path and ran lifecycle scripts from
that copy — collapsing the Release's own immutable location (`RELEASE_DIR`,
as every script computes it) and the permanent live deployment directory
(`canonical_path`) into the literal same directory. Real Applications'
scripts correctly assume these are two different places and copy content
between them, which self-collides when they're not.

**At fault:** Platform.

**Fix:** Lifecycle scripts now run in place from `release_storage_path`
(matching `backup.py`/`recovery.py`'s pre-existing, already-correct
convention) instead of a copy staged inside `canonical_path`. The live path
is passed to scripts explicitly via `RAH_ACTIVE_DEPLOYMENT_PATH`. 15 Golden
Fixture scripts updated to read the rendered `.env` via explicit
`--env-file` instead of relying on Compose's implicit directory-based
lookup (which only worked by the same accidental path collision).

**Status:** ✅ Fixed (`installation.py`/`update.py`, commit `8962624`; test
harness gap in `test_verification.py` fixed alongside, commit `b7d49c3`).
Full suite reconfirmed: 167 passed, 0 failed, real Postgres/Docker on
`or-stt`. Documented as slice **`B2+`** in the Period B task table.
**No real Application needed any change for this one** — confirmed by
tracing HCopilot's own `INSTALL_ROOT` default against Platform's
`deployments_path` default before assuming a fix was needed there.

---

### 4. HCopilot: configuration template read from the wrong directory

**What broke:** Fresh install failed: `sed: can't read
.../compose/.env.offline.template: No such file or directory` — the file
genuinely wasn't there.

**Root cause:** The RAH Packaging Engine always relocates a declared
`configuration.template` file into the built Release's own `configuration/`
directory, regardless of where the file lived in the app's own source tree
— confirmed directly against a real packaged `release.yaml`
(`configuration.template: configuration/.env.offline.template`).
`install_offline.sh`/`update_offline.sh` hardcoded
`compose/.env.offline.template` instead — an assumption that only ever
coincidentally worked while bug #3 (above) made `compose/` and
`configuration/` sit inside the same collapsed directory.

**At fault:** HCopilot (application-specific — but the underlying pattern
is general enough to recur in any app built by the shared Packager).

**Fix:** Both scripts now read from `configuration/.env.offline.template`.

**Status:** ✅ Fixed (HCopilot commit `a31aaaf`). Added to the Playbook as
**§13a**, explicitly scoped to apps that actually use the shared Packager
(an app with its own independent release-build pipeline keeps its own
valid convention — see the fleet check below).

**Fleet check performed (zero API cost, local inspection only):** of the 5
real apps, only HCopilot and `Healthcare_reporting_system_backup` actually
use the shared Packager (both have a `.rah/` engineering-answers
directory). STT-SCHEDULE, RESTful-API-Integration, and HCAT
(`Patient_Feedback`) each have their own independent, non-Packager
release-build scripts, and each app's own script already agrees with its
own build tooling's convention — self-consistent, not bugged.
`Healthcare_reporting_system_backup`'s script was already correct.
**Deliberately left unchanged** per explicit user decision — forcing the
Packager's `configuration/` convention onto them would be a regression, not
a fix. Whether any of the three should eventually migrate onto the shared
Packager is an open, non-urgent future decision.

---

### 5. HCopilot: `database/*.sql` is declared to be copied but never actually packaged

**What broke:** `cp: cannot stat '.../database/*.sql': No such file or
directory` during install.

**Root cause:** `install_offline.sh`/`update_offline.sh` copy
`$RELEASE_DIR/database/*.sql` to `$INSTALL_ROOT/database/` — files that
`backup_database.sh`/`restore_database.sh` genuinely need at runtime. But
nothing in HCopilot's `.rah/engineering-answers.json` declares a field that
causes the Packaging Engine to include `release-src/database/*.sql` (a
directory unrelated to the declared
`database.initialization.entrypoint`, `backend/scripts/ensure_database_exists.py`)
in a built Release. Every real Release's `database/` folder therefore
contains only the four Python db-init scripts — never the two `.sql`
files.

**At fault:** HCopilot's own Release Engineering (a genuine gap against
the Playbook's own §52 "Validate Release Self-Containment" requirement —
this specific dependency was never actually checked end-to-end before
today).

**Fix applied so far:** Made the copy non-fatal (`2>/dev/null || true`,
commit `dfe7023`) so the missing packaging doesn't block installation
itself.

**Status:** 🟡 **Partially fixed — install no longer blocked, but backup and
restore remain genuinely broken.** Needs a real decision before `B5`
(Backup/Update) exercises HCopilot for real: either declare
`release-src/database/*.sql` under some engineering-answers field so the
Packaging Engine includes it, or change `backup_database.sh`/
`restore_database.sh` to read the SQL from somewhere the Packager already
populates. **Not yet fixed at the root — tracked here so it isn't lost.**

---

### 6. Platform: lifecycle scripts run inside Platform's own isolated Docker network

**What broke:** `verify_installation.sh` reported `BACKEND HEALTH CHECK
FAILED`, `FRONTEND CHECK FAILED`, `FRONTEND PROXY CHECK FAILED` —
even though the real application was completely healthy. Confirmed
directly: `curl http://localhost:8090/health` from the real `or-stt` host
returned `{"status":"ok"}`; the exact same command from inside
`platform-backend-1` (the container that actually ran the script) returned
nothing (`000`).

**Root cause:** Platform's `run_script` executes lifecycle scripts as a
subprocess of Platform's own backend container. That container runs on its
own isolated Docker network (`platform_default` bridge, not host
networking) — so `localhost` inside it does *not* mean the same thing as
`localhost` on the real host, even though every lifecycle script (written
to run on the real Debian host, per the RAH Application Release &
Deployment Standard) assumes exactly that. The one check that *did* pass
(the database check) only worked because it uses `docker compose exec`
via the Docker socket, which bypasses network namespacing entirely — every
plain `curl localhost:<port>` check does not.

**At fault:** Platform (a structural deployment-configuration issue, not
anything any application's script could have avoided).

**Fix:** Not yet applied. Diagnosed as needing `network_mode: host` on
Platform's own backend service — but this has real ripple effects,
discovered before applying anything: Platform's `RAH_DATABASE_URL`
currently reaches Postgres via the bridge network's internal DNS name
(`postgres:5432`), which breaks under host networking; and the Platform
frontend's `nginx.conf` hardcodes `proxy_pass http://backend:8000`, which
would break the same way if backend leaves the bridge network. A complete
fix needs: backend on host networking, Postgres's port exposed to the host
(loopback-only) with `RAH_DATABASE_URL` repointed to `localhost`, and
either the frontend also moved to host networking (with `nginx.conf`
listening on `8080` directly instead of `80`) or another way found for it
to reach backend. Also needs a port-conflict check against `or-stt`'s other
running containers before applying (`8000`, `8080`, `5432` are currently
only bound via Docker's own port-publishing, not directly on the host, so
moving to host networking would newly claim those exact host ports
directly).

**Status:** ✅ Fixed. `platform/docker-compose.yml`: `network_mode: host` on
both `backend` and `frontend`; Postgres published to the host on loopback
only (`127.0.0.1:5432:5432`); `RAH_DATABASE_URL` repointed from the
bridge-network DNS name `postgres` to `localhost` (matching `config.py`'s
own existing default); `platform/frontend/nginx.conf` repointed from
`backend:8000` to `localhost:8000` and switched to `listen 8080` directly
(no more host-port remapping under host networking) (commit `8cb1955`).
Verified directly: `curl localhost:8000/...` from inside
`platform-backend-1` now returns `200` (previously `000`). Full Platform
test suite reconfirmed clean afterward: 167 passed, 0 failed, real
Postgres/Docker on `or-stt`. Documented in the Playbook as **§18a**.

---

### 7. HCopilot: Docker Compose project name never pinned to the manifest's declared identity

**What broke:** After bug #6 was fixed, install actually succeeded (the
app's own `install_offline.sh` exited `0`, real containers came up
healthy) — but Platform's own post-install verification still reported
`FAILED`: `container_existence: Missing containers for services:
['sqlserver', 'backend', 'frontend']`, even though those containers were
genuinely running.

**Root cause:** `start_stack.sh` runs `docker compose up -d` from
`$INSTALL_COMPOSE_DIR` (`/opt/rah/apps/hcopilot/compose`) without ever
setting `COMPOSE_PROJECT_NAME` or passing `-p`. Compose's documented
fallback — the basename of the directory containing the Compose file —
kicked in, producing project name `compose` (the directory is literally
named `compose/`), not `hcopilot`. Every real container ended up labeled
`com.docker.compose.project=compose`. Platform's verification correctly
filters real containers by the manifest's own declared
`compose_project_name` (`hcopilot`, per the Release Contract) and
therefore found zero matches — a real violation of this Playbook's own
§9 ("Establish a Stable Docker Compose Identity": *"Do not allow Docker
Compose to derive the production application identity from... another
staging-directory name"*), not a Platform bug.

**At fault:** HCopilot (application-specific).

**Fix:** `_common.sh` now exports `COMPOSE_PROJECT_NAME="$APP_SLUG"` once,
sourced by every lifecycle script — no per-script changes needed.

**Status:** ✅ Fixed (HCopilot commit `9aef4db`). Verified for real: fresh
install of `HCopilot_Release_1.0.7` via Platform `SUCCEEDED` end to end
(`RECORDING_RESULT`, `verification_status: PASS`), real containers now
correctly labeled `hcopilot-*`/`com.docker.compose.project=hcopilot`,
frontend/backend independently confirmed reachable and healthy from
outside Platform. **`B3` (Fresh Installation) is DONE.**

---

## 2026-08-21 — Period B, `B4` (Verification/Reconciliation)

### 8. Platform: canonical deployment path and backups path never bind-mounted to the real host

**What broke:** Nothing visibly — this was found by independently tracing
real state during `B4`, not by a failure. `install_offline.sh` genuinely
wrote `.env`, `docker-compose.yml`, `INSTALLED_VERSION`,
`DEPLOYMENT_HISTORY.log`, `database/`, `backups/`, and `scripts/*` to
`/opt/rah/apps/hcopilot` — but that path existed only inside
`platform-backend-1`'s own container filesystem. Confirmed directly:
`docker inspect platform-backend-1`'s real mounts covered
`release_storage_path`, `contracts/1.0`, and the Docker socket only — no
mount for `deployments_path` at all. The real `or-stt` host's own
`/opt/rah/apps/hcopilot` was nearly empty.

**Root cause:** Platform's own Compose definition for the `backend`
service never declared a bind mount for `config.deployments_path`
(`/opt/rah/apps`) or `config.backups_path` (`/opt/rah/backups`) — a
missing volume declaration, the same category of gap `release_storage_path`
already correctly has. Generic to every real Application, not
HCopilot-specific.

**At fault:** Platform.

**Why it mattered:** `installation.read_rendered_env()` — which `PL8a`'s
entire update path uses to preserve secrets across an update (§7.16) —
depends on this file surviving on disk. It didn't, durably: only as long
as that one `platform-backend-1` container instance was never recreated.
`backup.py` writes real backup artifacts under `config.backups_path`,
deliberately isolated from replaceable container filesystems per §9.20 —
same gap, same consequence. `B5` (Update Path, the next slice) would have
hit this immediately.

**Fix:** Added two bind mounts to `or-stt`'s own local, untracked
`docker-compose.override.yml` (not the repo's tracked
`platform/docker-compose.yml`, which stays pointed at Golden Fixtures):
`/opt/rah/apps:/opt/rah/apps` and `/opt/rah/backups:/opt/rah/backups`,
identity-mapped to match `config.py`'s own existing container-path
defaults. Before recreating `platform-backend-1`, the trapped
`/opt/rah/apps/hcopilot` contents were rescued via `docker cp` and
restored into the new host-backed path afterward, and the real DB
password was independently confirmed recoverable from
`hcopilot-sqlserver-1`'s own env as a second safety net. The real
`hcopilot-*` containers (created via the Docker socket against the host
daemon, not stored inside `platform-backend-1`) were confirmed untouched
throughout.

**Status:** ✅ Fixed. Verified for real: `platform-backend-1` recreated
with the new mounts; `hcopilot-*` containers confirmed still `Up`/healthy
and unaffected; restored files confirmed genuinely present on the real
host filesystem (not just inside the container); `verify_deployment`
(`MANUAL`) and `reconcile_application_state` both re-run afterward,
reporting `PASS`/`CONSISTENT` — identical to before the recreate. Full
Platform test suite reconfirmed clean afterward: **167 passed, 0 failed,
575.39s**, matching `B3`'s own baseline exactly. Documented as slice
**`B3+`** in the Period B task table (all seven Testing Record items
PASS).

### 9. Platform: `database_connectivity`/`migration_state` verification checks are unimplemented stubs, non-mandatory

**What was found:** Running independent `MANUAL` verification against the
real, SQL-Server-backed HCopilot deployment (`database.required: true`)
returned `database_connectivity`/`migration_state` as `NOT_EXECUTED`
("...checking is not implemented in Period A") rather than a real result
— yet the overall verification run still reported `PASS`, because neither
check is in `verification.py`'s `MANDATORY_CHECK_KEYS`.

**Root cause:** Deliberate, and explicitly anticipated in `verification.py`'s
own module docstring, written during `PL7`: "no real DB connectivity
checking is built in Period A." HCopilot is the *first* real Application
with `database.required: true` that this code has ever run against —
every Golden Fixture used through `PL7`/`PL9b` had `database.required:
false`, so this deferred scope never had a live case to surface it until
now. Same applies to `backend_health`/`frontend_reachability`: both check
for the literal string `"backend_health"`/`"frontend_reachability"`
inside the manifest's own `verification.required_checks` list, but
HCopilot's `required_checks` are free-text prose sentences (e.g. "Backend
/health returns HTTP 200 on BACKEND_PORT"), not the Contract's standard
machine-readable identifiers — so both always resolve `NOT_APPLICABLE`
for HCopilot specifically, structurally, regardless of real backend/
frontend health.

**At fault:** Not a defect against current scope — an already-documented
Period A deferral, now concretely relevant for the first time.

**Independent proof gathered instead (`B4`'s own job):** direct `sqlcmd`
query inside `hcopilot-sqlserver-1` confirmed `HCopilotDB.Doctors` = 18
rows, `HCopilotDB.EDbeds` = 24 rows (genuinely reachable and populated,
matching the manifest's own required-check text exactly); direct `curl`
from the real host confirmed backend `/health` → `200`, frontend root →
`200`, and the frontend→backend nginx proxy path → `200`.

**Status:** 🟡 **Open, tracked, not blocking.** A real, now-concrete gap:
Platform cannot yet automatically detect a genuine SQL Server connectivity
failure for HCopilot on its own. Real implementation would mean a `docker
exec sqlcmd` check (mirroring the release's own manifest text) plus
teaching the Packager to emit the Contract's standard check identifiers
into `required_checks` instead of prose. Left open deliberately — implementing
new verification capability is a scope decision distinct from `B4`'s own
completion gate, which `B4` satisfies through direct, independent evidence
instead (above). Worth a decision before it recurs for other
database-required apps.
