# Complete Briefing — RAH Offline Installation Platform

Written by the Claude session on the online lab VM, for the Claude session working
directly on this Windows machine (the Legion). Read this whole thing before touching
anything — it replaces and consolidates the smaller handoff files sent earlier
(`PROMPT_FOR_LENOVO_CLAUDE.md`, `EXPLANATION_FOR_LENOVO_CLAUDE_pool_colons.md`,
the export `README.md`). Those are still on disk but this is the current, complete state.

---

## 1. Where everything is right now

- **Your working repo:** `C:\Users\it\Documents\GitHub\Air-Gapped-System-Platform`
  (already `infrastructure/rah-oip-releases/...` populated — see §4 for exact status)
- **Raw export dump (reference material, not meant to be committed as-is):**
  `C:\Users\it\Desktop\RAH-Offline-Platform-Export\`
- **The other 4 hospital application source repos** (separate from the platform project,
  these are the actual applications the platform will eventually manage):
  - `C:\Users\it\Documents\HCopilot\HCopilot`
  - `C:\Users\it\Documents\GitHub\STT-SCHEDULE`
  - `C:\Users\it\Documents\GitHub\voice-project_Deployment`
  - `C:\Users\it\Documents\GitHub\Healthcare_reporting_system_backup` (the "Indicator" app)

## 2. What this project actually is, and where it came from

Started as a much smaller thing: a DVD/USB kit to turn a blank offline Debian server into
one that could run Docker + hospital applications, since the real target machines are
**permanently air-gapped** — no internet, by design, forever. That kit
(`offline-debian-server-kit/` in the export, and its more disciplined successor
`rah-oip-releases/RAH-OIP-1.0.0_Debian13_2026-07-09/`) has been built, broken, fixed, and
re-validated repeatedly on a real two-VM lab setup (see §6).

**The idea has since expanded** (the user's own words) into something bigger: a UI-based
"platform" that sits on top of the release architecture and makes installing/updating
hospital applications easy through a control panel instead of raw shell scripts and
manual `.env` editing. The user has already reasoned through what this platform is and
isn't (their own planning doc — ask them for it directly if it's not already in your
context, it was titled something like "Idea Definition ; Is it Worth It.md"). The core
philosophical framing, in their words:

> This solution is only a UI release architecture based software. Its main task is to
> make it easy to install new software and custom release-folder-based applications, and
> update them, and keep track of the version/historical change. It is NOT a versioning
> system. It does not control whether an update goes backward or forward. It is a smart,
> informative UI executor of installation steps — port selection, password generation,
> reading what's already installed and what version.

Explicit non-goals the user stated: not Portainer, not a Docker management replacement,
not a second competing definition of what a release is. **The release architecture
defines the release. The platform consumes and executes that definition.**

The user's own notes end with an unresolved next step they explicitly planned but hadn't
done yet: **"Stage 1 — Identification and Resolution of Existential Threats"** — working
through what could make the platform concept fail *before* writing implementation code.
That's still open. Don't skip past it into UI/framework decisions without them.

## 3. The one thing to get right early: the release/platform contract

The user has already identified this as the load-bearing architectural piece: a
**stable, machine-readable contract** between what an "Application Release" looks like
(folder shape, script names, config conventions) and what the platform can safely assume
about it. Without this, every release folder — built by different Claude sessions at
different times — risks being shaped slightly differently, and a platform can't safely
automate against inconsistent input.

`rah-oip-releases/RAH-OIP-1.0.0_Debian13_2026-07-09/` already has a `MANIFEST.yaml`,
`COMPATIBILITY_MATRIX.md`, and `VALIDATION_REPORT.md` — this is a reasonable starting
shape for that contract, but it was designed for a human building a DVD, not necessarily
for a platform consuming it programmatically. Worth deciding with the user whether it
needs to change shape for that purpose, or just needs a schema written down.

## 4. Current status of the APT pool transport (just resolved)

`01_APT_Repository/` in the copied release now contains exactly:
- `Packages` — the dpkg-scanpackages index, correct as-is
- `pool.tar.gz` — all 312 real `.deb` packages, archived as one blob
- `README.md` — explains why and how to extract it

**Why archived instead of loose files:** 58 of the 312 real Debian package filenames
contain a literal `:` (the "epoch" version prefix, e.g.
`docker-ce-cli_5:29.6.1-1~debian.13~trixie_amd64.deb`) — a character Windows NTFS cannot
represent in a filename at all. Loose-file copy attempts silently failed for exactly
those 58 files (left as 0 bytes) while the other 254 copied fine — confirmed and
diagnosed together across both sessions. The archive sidesteps this because tar/zip
*formats* don't care what characters are in an internal entry name, only the OS
filesystem does when something extracts it raw.

**Extract `pool.tar.gz` only on a Linux machine** (never Windows) at the point it's
actually needed — recreates `pool/` exactly matching the `Filename: pool/<name>.deb`
paths already in `Packages`. Verified before transfer: extracts to exactly 312 files,
zero corruption, from a checksummed source.

**Open question, not yet decided:** whether this archive-blob approach is the permanent
answer, or whether the pool should instead become a generated build artifact (not
committed to git at all, regenerated fresh from a package list on a Linux build machine
each release, matching how you wouldn't commit `node_modules`). Discuss with the user —
don't just pick.

## 5. What's been tested against real hospital applications, and what broke

Four application release packages have been through real validation on the offline
air-gapped simulator VM (see §6). This matters for the platform because these are exactly
the kinds of release folders it will need to install/update automatically — their real
bugs are a preview of what the platform needs to handle gracefully, or what release
authors need to stop doing.

**HCopilot** — SQL Server-backed. Found: a forgotten/placeholder `MSSQL_SA_PASSWORD`
(literally the string `REPLACE_WITH_STRONG_PASSWORD`) doesn't just fail — it fails SQL
Server's own password-complexity check, causing an opaque "container unhealthy" error
many minutes later with no obvious link back to the real cause. Fixed by adding a fail-fast
placeholder/complexity check at the top of `install_offline.sh`. **A platform that
generates passwords automatically for the user sidesteps this whole bug class entirely**
— worth treating as a first-class requirement, not a nice-to-have.

**STT-SCHEDULE** — Postgres-backed, includes pgAdmin. Found: `install_offline.sh`
creates a data directory as root (via `sudo`), but the `dpgage/pgadmin4` container runs
as a fixed non-root UID (5050) — permission denied, pgAdmin crash-loops forever, and the
symptom (a hung HTTP request) gives no hint the real cause is a UID mismatch. Fixed with
an explicit `chown` after directory creation.

**Voice Project (Blood Bank)** — SQL Server-backed, includes a Whisper speech-to-text
container. Found, twice: (1) the Whisper container tried to download its model from the
internet at startup — obviously fatal on an air-gapped target, fixed by bundling the
model as a local asset extracted at install time; (2) a database-verification script
referenced host-relative paths from inside a container where they don't exist, fixed by
bind-mounting — which then hit the *exact same* UID-permission bug class as pgAdmin, just
in a new spot (SQL Server's container runs as UID 10001, mounted dirs were root-only).
Also found and fixed, separately: a missing WebSocket header-forwarding rule in nginx
(silently downgraded chat functionality to broken), and hardcoded CDN dependencies
(Google Fonts, Chart.js) that fail silently offline — vendored locally instead.

**Indicator (Healthcare Reporting)** — no database, simplest of the four. Passed clean
on first try. One design note found worth knowing: its frontend has a **hardcoded**
backend port baked into the built JS bundle (`8001`) — changing `BACKEND_PORT` in `.env`
alone breaks it without also rebuilding the frontend image. **This is directly relevant
to the platform's "let the user pick any free port" feature** — some existing release
images may not actually support arbitrary port reassignment without a rebuild, and the
platform needs to either detect/flag that, or the release contract needs to require
frontends to read their API base URL from runtime config, never bake it in at build time.

## 6. The three-way recurring bug pattern (design around this explicitly)

**pgAdmin (UID 5050), SQL Server reading mounted validation scripts (UID 10001), and
DBeaver's own driver cache** all hit variants of the identical root cause: **a Docker
container running as a fixed non-root UID couldn't read/write a host-mounted directory
that a root-run install script had created without fixing ownership afterward.** Three
different applications, three independent discoveries of the same mistake. If the
platform ever generates or manages install directories on the user's behalf, it should
bake in "always fix ownership for the actual runtime UID" as a standard step, not
something each release author has to remember separately every time.

## 7. The lab validation pipeline (for future testing)

There's a two-VM setup used to validate all of the above, hosted on this Legion via
Hyper-V:
- **Online Debian VM** ("OR-STT") — has internet, where release engineering happens (the
  Claude session that wrote this briefing runs there).
- **Offline Validation VM** ("Offline-AirGapped-Simulator") — genuinely no internet
  access, simulates the real hospital target. Every install/verify script gets run there,
  from a clean Hyper-V snapshot, before being trusted.

If the platform needs further application-release testing (very likely, given §5), that
pipeline already exists and works — it doesn't need to be rebuilt. The user can relay a
request back to the online-VM session, or you can ask them how to reach it directly if
you need to drive it yourself. Full connection details live in
`docs/RAH-OIP_LAB_ENVIRONMENT_REFERENCE.md` in the export folder — but note IPs in there
drift over time (Wi-Fi network changes), always re-verify rather than trust a remembered
value.

## 8. What NOT to do

- Don't start writing platform UI/framework code before working through the
  release/platform contract question (§3) and the existential-threats stage the user's
  own notes call for.
- Don't assume structural decisions (repo layout, how the APT pool gets stored long-term,
  what the contract schema looks like) — ask the user, the same way this session did
  before committing to the tarball approach in §4.
- Don't re-litigate or redo the four application validations in §5 from scratch — the
  bugs found there are real, confirmed, and mostly already fixed at the source. Build on
  that record rather than rediscovering it.
