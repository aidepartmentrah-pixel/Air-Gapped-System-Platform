---
name: stt-schedule-release-validation
description: "STT-SCHEDULE (OR voice-scheduling app) offline release — where it lives, real architecture, and a reproducible password bug found during fresh-install validation"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5d5a7424-23ee-44c3-bf0f-1ee7a18a69fc
---

**STT-SCHEDULE** = a hospital operating-room voice-scheduling/tracking app (12 ORs,
OR1–OR12, seeded by migrations; nurse control panel, admin panel, public wall
dashboard, local Vosk speech recognition). Release packages live on the Legion at
`C:\Users\it\Documents\GitHub\STT-SCHEDULE\release` — a separate app from both
RAH-OIP itself and [[voice-project-release-validation]]; shares the same lab
infrastructure, see [[rah-oip-lab-topology]].

**Real architecture actually matches its own docs** (unlike the Voice Project,
whose plan doc was wrong) — genuinely PostgreSQL 15-alpine + Alembic migrations,
FastAPI backend, static frontend served via its own nginx (baked into the image,
no bind mount), pgAdmin4 8.14 bundled for DB browsing. Compose services:
`postgres`, `pgadmin`, `migrate` (one-shot), `init-admin` (one-shot), `backend`,
`frontend`. Default ports: backend 8002, frontend 8081, pgAdmin 5051 — chosen
specifically to avoid colliding with other apps' defaults (8001/8080/5050) on a
shared multi-app host.

**Bug found during validation (2026-07-22), not yet reported upstream:** the
release builds `DATABASE_URL` by directly interpolating `POSTGRES_PASSWORD` into
a `postgresql+asyncpg://user:password@postgres:5432/db` string with no
percent-encoding anywhere in `docker-compose.offline.yml` or the backend/migrate
code. A password containing `@` (e.g. `P@ssw0rd`) breaks URL parsing — SQLAlchemy's
`make_url` treats the *first* `@` as the userinfo/host separator, so `postgres`
becomes part of the password and the real host becomes garbage like
`ssw0rd@postgres`, which then fails DNS resolution (`socket.gaierror: Name or
service not known`) in the `migrate` container, cascading to `init-admin`,
`backend`, and `frontend` never starting (compose depends_on chain blocks them).
**Symptom looks like a network/DNS problem but is actually a password-content
bug.** Workaround: never put `@` (or other URL-reserved characters: `:/?#[]!$&'()*+,;=`
and space) in `POSTGRES_PASSWORD` for this app. `PGADMIN_DEFAULT_PASSWORD` and
`ADMIN_PASSWORD` aren't URL-embedded so they're not affected the same way, but
using one uniform safe password for all three is simplest.

**Also found:** Postgres is not exposed to the host in the shipped compose file —
only reachable inside the Docker network by hostname `postgres` (used by the
bundled pgAdmin). To connect an external tool like DBeaver (preinstalled on the
offline VM per [[rah-oip-environment-reference-file]]'s `GoldenSnapshot-WithRAHOIP`),
add a `ports: ["5432:5432"]` block to the `postgres` service in the *deployed*
compose file (`/opt/stt-schedule/docker-compose.offline.yml`), then
`docker compose --env-file .env -f docker-compose.offline.yml up -d postgres` to
recreate just that container — the data volume is untouched by this.

**Status:** fresh install of 0.1.0 validated clean on the Offline Validation VM
(10.10.10.2) starting from `GoldenSnapshot-WithRAHOIP` — all of
`verify_installation.sh`'s checks pass (backend/frontend/pgAdmin reachable, 12 OR
rows seeded), Postgres port exposed and DBeaver-equivalent auth confirmed working
end-to-end (`psql` over the host-published port with app credentials). Used
`POSTGRES_PASSWORD=PGADMIN_DEFAULT_PASSWORD=ADMIN_PASSWORD=Passw0rd123` (URL-safe,
easy to type) for this validation run — not a production credential.
