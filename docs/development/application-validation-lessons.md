# Application Validation Lessons

Distilled from real install/verify runs of four hospital application releases on the
offline air-gapped lab VM (see `infrastructure/COMPLETE_BRIEFING_FOR_LENOVO_CLAUDE.md`
§5–§7 for the full, original account). This is not a retelling for its own sake — every
item below is a concrete constraint on what the Packaging Engine, the Release Contract,
and the Offline Installation Platform need to handle, because it already broke something
real once.

Source repos for the four applications referenced here (separate from this platform
project — these are applications the platform will eventually manage):

- `C:\Users\it\Documents\HCopilot\HCopilot`
- `C:\Users\it\Documents\GitHub\STT-SCHEDULE`
- `C:\Users\it\Documents\GitHub\voice-project_Deployment`
- `C:\Users\it\Documents\GitHub\Healthcare_reporting_system_backup` (the "Indicator" app)

(HCAT — `Patient_Feedback` backend + `Front_End_Feedback_Analysis` frontend — is a
separate, fifth real application, not yet run through this validation pipeline. See
`CURRENT.md` for the HCAT vs. HCopilot distinction; they are unrelated applications
despite the similar names.)

## What broke, application by application

**HCopilot** (SQL Server-backed) — a forgotten/placeholder `MSSQL_SA_PASSWORD`
(literally the string `REPLACE_WITH_STRONG_PASSWORD`) doesn't just fail cleanly — it
fails SQL Server's own password-complexity check, surfacing many minutes later as an
opaque "container unhealthy" error with no obvious link back to the real cause. Fixed at
the source with a fail-fast placeholder/complexity check at the top of
`install_offline.sh`.

**STT-SCHEDULE** (Postgres-backed, includes pgAdmin) — `install_offline.sh` created its
data directory as root (via `sudo`), but the `dpage/pgadmin4` container runs as a fixed
non-root UID (5050). Permission denied, pgAdmin crash-loops forever, and the visible
symptom (a hung HTTP request) gives no hint the real cause is a UID mismatch. Fixed with
an explicit `chown` after directory creation.

**Voice Project (Blood Bank)** (SQL Server-backed, includes a Whisper speech-to-text
container) — three separate issues: (1) the Whisper container tried to download its
model from the internet at startup, fatal on an air-gapped target — fixed by bundling
the model as a local asset extracted at install time; (2) a database-verification script
referenced host-relative paths from inside a container where they don't exist, fixed by
bind-mounting — which then hit the same UID-permission bug class as pgAdmin, in a new
spot (SQL Server's container runs as UID 10001, mounted dirs were root-only); (3) a
missing WebSocket header-forwarding rule in nginx silently downgraded chat functionality,
and hardcoded CDN dependencies (Google Fonts, Chart.js) failed silently offline — both
fixed, the latter by vendoring assets locally.

**Indicator (Healthcare Reporting)** (no database, simplest of the four) — passed clean
on first try. One design note worth keeping: its frontend has a backend port
(`8001`) **hardcoded into the built JS bundle**. Changing `BACKEND_PORT` in `.env` alone
does not work — the frontend image has to be rebuilt too.

## Patterns that generalize (these are the load-bearing part)

**1. The UID/ownership bug hit three unrelated applications independently:** pgAdmin
(UID 5050), SQL Server reading mounted validation scripts (UID 10001), and separately
DBeaver's own driver cache. Same root cause every time — a Docker container running as a
fixed non-root UID couldn't read/write a host-mounted directory that a root-run install
script created without fixing ownership afterward.

> **Consequence for this project:** if the Offline Installation Platform ever creates or
> manages install directories on the user's behalf, "fix ownership for the actual
> runtime UID" needs to be a standard, built-in step — not something each release author
> has to remember to do correctly every single time.

**2. Placeholder/weak secrets fail late and unhelpfully, not immediately.**

> **Consequence:** a platform that generates strong passwords automatically for the user
> sidesteps this entire bug class. Worth treating as a first-class platform requirement,
> not a nice-to-have.

**3. Not every existing release image actually supports free port reassignment**
— some bake their backend URL into a frontend build rather than reading it at runtime.

> **Consequence:** the Release Contract needs to either require frontends to read their
> API base URL from runtime config (never bake it in at build time), or the platform
> needs a way to detect/flag "this release doesn't actually support arbitrary port
> reassignment" rather than silently offering a broken option.

**4. Internet-dependent runtime behavior (model downloads, CDN assets) is invisible
until you actually test offline** — every one of these passed a superficial "does it
start" check and only failed once genuinely air-gapped.

> **Consequence:** validation has to run on the real offline-simulator VM, not just
> checked by reading the Dockerfiles/compose files.

## What this means for the Release Contract and Packager work specifically

These four bug classes are exactly the kind of thing the Release Contract's
`validation-rules.json` should be able to catch mechanically before a release ships,
rather than relying on each release author remembering four unrelated lessons learned
the hard way on this project already. Worth reviewing against the contract once the four
executable files exist.
