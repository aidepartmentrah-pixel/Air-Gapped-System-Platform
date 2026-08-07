# PostgreSQL Container Guide

This kit ships PostgreSQL 16.14 (`postgres:16.14`, loaded from
`03_database_images/postgres/postgres-16.14.tar`).

## Starting a container manually (for testing outside Portainer)

```
docker run -d \
  --name postgres \
  --restart unless-stopped \
  -e "POSTGRES_PASSWORD=<choose a strong password>" \
  -e "POSTGRES_USER=postgres" \
  -p 5432:5432 \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:16.14
```

Notes:
- `-v postgres_data:/var/lib/postgresql/data` is a **named Docker volume** — this is what
  makes the database survive container restarts/recreation. Never delete this volume
  unless you intend to permanently destroy the database.
- Port 5432 only needs to be published if you want to connect from DBeaver or another
  tool outside Docker. If only the backend container talks to it, you can rely on the
  Docker network instead and omit `-p 5432:5432`.

## Checking it started correctly

```
docker logs postgres
```

Expected, near the end of the output:
```
database system is ready to accept connections
```

## One PostgreSQL instance, multiple project databases

A single PostgreSQL container can host multiple project databases, each created by that
project's install scripts (`CREATE DATABASE <project_name>;`). Each project's Database
Package (Prompt 1B) handles creating its own database, schema (via Alembic if already in
use), lookup data, and users inside this same instance.

## Connecting with DBeaver

See `DBEAVER_GUIDE.md` — use host `localhost` (or the server's IP from another machine),
port `5432`, database name as created by the project, and the `postgres` superuser or a
project-specific role created by that project's install scripts.
