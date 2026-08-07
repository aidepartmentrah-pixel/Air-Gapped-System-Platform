# DBeaver Guide

DBeaver Community Edition is a database GUI client, installed by
`07_install_scripts/install_dbeaver.sh` from `04_database_tools/dbeaver/dbeaver-ce_26.1.2_amd64.deb`.
It bundles its own Java runtime, so no extra dependencies are needed.

## Launching DBeaver

From the applications menu, or from a terminal:
```
dbeaver-ce
```

## Connecting to SQL Server

1. **Database** menu → **New Database Connection**.
2. Select **Microsoft SQL Server** → **Next**.
3. Fill in:
   - Host: `localhost` (if run on the same server) or the server's IP address
   - Port: `1433`
   - Database: leave blank to connect to the instance, or type a specific database name
   - Authentication: **SQL Server Authentication**
   - Username: `sa` (or a project-specific login)
   - Password: the `MSSQL_SA_PASSWORD` you set when starting the container
4. Click **Test Connection**. The first time, DBeaver may ask to download the SQL Server
   JDBC driver — **this requires internet and will fail offline**. If prompted, cancel
   the download dialog; the driver must instead be pre-bundled with DBeaver's offline
   package, or manually placed in DBeaver's driver folder ahead of time. Check
   `TROUBLESHOOTING.md` if the built-in driver is missing.
5. Click **Finish**.

## Connecting to PostgreSQL

1. **Database** menu → **New Database Connection**.
2. Select **PostgreSQL** → **Next**.
3. Fill in:
   - Host: `localhost` (if run on the same server) or the server's IP address
   - Port: `5432`
   - Database: the project's database name
   - Username: `postgres` (or a project-specific role)
   - Password: the `POSTGRES_PASSWORD` you set when starting the container
4. Click **Test Connection**, then **Finish**.

## Viewing all project databases on one instance

Once connected to the SQL Server or PostgreSQL instance, expand the connection in the
left-hand **Database Navigator** tree — every project's database hosted on that same
container appears as a separate node underneath.
