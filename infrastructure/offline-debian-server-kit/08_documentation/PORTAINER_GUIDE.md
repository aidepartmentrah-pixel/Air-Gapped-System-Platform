# Portainer Guide

Portainer CE gives you a web dashboard to manage Docker containers without typing
commands. Installed by `07_install_scripts/install_portainer.sh`.

## Opening Portainer

1. On the offline server, find its IP address:
   ```
   hostname -I
   ```
2. From any machine on the same network, open a browser to:
   ```
   https://<server-ip>:9443
   ```
   (The `https` and the self-signed certificate warning are expected — click through /
   "Advanced -> Proceed" the first time.)

## First-time setup

1. On first visit, Portainer asks you to create an admin username and password. Choose a
   strong password and record it somewhere safe (e.g. a password manager) — there is no
   password reset without database access.
2. Select "Get Started" / "Local" environment — Portainer will automatically detect the
   Docker engine running on this same server via the mounted `docker.sock`.

## Verifying images are loaded

1. In the left sidebar, click **Images**.
2. You should see:
   - `mcr.microsoft.com/mssql/server:2022-pinned`
   - `postgres:16.14`
   - `portainer/portainer-ce:dd43259`
   (loaded by `load_database_images.sh` and the Portainer install script itself)

## Creating or updating a stack (for application deployment later)

1. Left sidebar → **Stacks** → **Add stack**.
2. Give it a name (e.g. the application's name).
3. Paste in the application's `docker-compose.yml` (produced by the Dockerization prompt
   for that project).
4. Under **Environment variables**, add the values from that project's `.env.offline`
   file — one variable per row.
5. Click **Deploy the stack**.
6. To update later: open the stack, edit the compose content or environment variables,
   and click **Update the stack**.

## Viewing logs

1. Left sidebar → **Containers**.
2. Click the container name.
3. Click the **Logs** tab. Use the refresh icon or enable "Auto-refresh" to follow live output.

## Restarting / stopping services

- From **Containers**, select the checkbox next to one or more containers, then use the
  **Restart** or **Stop** button in the toolbar above the list.
- From a **Stack** page, use **Stop this stack** / **Start this stack** to affect every
  container in that application at once.

## Confirming SQL Server is running

1. Left sidebar → **Containers**.
2. Find the container using the `mcr.microsoft.com/mssql/server` image.
3. Status column should read **running** (green).
4. Click the container name → **Logs** tab. Expect a line similar to:
   ```
   SQL Server is now ready for client connections.
   ```
