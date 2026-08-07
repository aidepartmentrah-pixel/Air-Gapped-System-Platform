# SQL Server Container Guide

## Important: editions and this image

This kit ships **one** SQL Server Docker image
(`mcr.microsoft.com/mssql/server:2022-pinned`, loaded from
`03_database_images/sqlserver/mssql-server-2022-pinned.tar`). Microsoft does not publish
separate images per edition — every edition (Express, Developer, Standard, Enterprise) is
the exact same image. **The edition is chosen when you start the container**, via the
`MSSQL_PID` environment variable.

This kit defaults to:
```
MSSQL_PID=Express
```

Express edition is free and licensed for limited production use, with these caps:
- Max database size: 10 GB per database
- Max 1 GB buffer pool memory used by the engine
- Max 4 CPU cores utilized

If a hospital application's database will exceed 10 GB, do not use Express — you will
need a real Standard/Enterprise license key, set as:
```
MSSQL_PID=<your license key>
```

## Starting a container manually (for testing outside Portainer)

```
docker run -d \
  --name sqlserver \
  --restart unless-stopped \
  -e "ACCEPT_EULA=Y" \
  -e "MSSQL_SA_PASSWORD=<choose a strong password>" \
  -e "MSSQL_PID=Express" \
  -p 1433:1433 \
  -v mssql_data:/var/opt/mssql \
  mcr.microsoft.com/mssql/server:2022-pinned
```

Notes:
- `ACCEPT_EULA=Y` is required — the container refuses to start without it.
- `MSSQL_SA_PASSWORD` must satisfy SQL Server's complexity rules (at least 8 characters,
  with uppercase, lowercase, digits, and symbols).
- `-v mssql_data:/var/opt/mssql` is a **named Docker volume** — this is what makes the
  database survive container restarts/recreation. Never delete this volume unless you
  intend to permanently destroy the database.
- Port 1433 only needs to be published (`-p 1433:1433`) if you want to connect from
  DBeaver/SSMS/Azure Data Studio running outside Docker. If only the backend container
  talks to it, you can omit the port publish and rely on the Docker network instead.

## Checking it started correctly

```
docker logs sqlserver
```

Expected, near the end of the output:
```
SQL Server is now ready for client connections. This is an informational message; no user action is required.
```

## One SQL Server instance, multiple project databases

Per RAH Lab policy, a single SQL Server container can host every project's database.
Each project's install scripts (from its Database Package, Prompt 1A) create their own
database by name inside this same instance — do not run a separate SQL Server container
per project.

## Connecting with DBeaver

See `DBEAVER_GUIDE.md` — use host `localhost` (or the server's IP from another machine),
port `1433`, and the `sa` user with the password you set above, or a project-specific
login created by that project's install scripts.
