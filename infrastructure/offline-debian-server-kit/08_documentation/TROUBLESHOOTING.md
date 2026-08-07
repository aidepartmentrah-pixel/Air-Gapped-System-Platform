# Troubleshooting

## `docker: command not found`

Docker Engine is not installed or not on the PATH. This kit cannot install Docker
without internet access — escalate to whoever provisioned this server.

## `systemctl status docker` shows `inactive (dead)` or `failed`

```
sudo systemctl start docker
sudo systemctl status docker --no-pager
```
If it fails to start, check `journalctl -u docker --no-pager | tail -50` for the reason
(common causes: corrupted `/var/lib/docker`, disk full, conflicting storage driver).

## `docker ps` → "permission denied while trying to connect to the Docker daemon socket"

Your user isn't in the `docker` group yet:
```
sudo usermod -aG docker $USER
```
Then **log out and log back in** (or reboot) — group membership only applies to new
sessions — and try again.

## `docker load -i <file>.tar` fails or hangs

1. Check the file wasn't truncated during USB/DVD transfer:
   ```
   sha256sum -c CHECKSUMS.txt
   ```
   If it says `FAILED` for that file, re-copy the kit from the original media.
2. Check disk space: `df -h /var/lib/docker` — Docker needs room to unpack layers.

## `dpkg -i` reports "dependency problems - leaving unconfigured"

This means a required `.deb` is missing from the kit's package set. Since this server has
no internet, you cannot run `apt-get install -f` to fetch it automatically. Check exactly
which package name is missing from the error output, then:
- If it's a DBeaver or Obsidian dependency: check `05_documentation_tools/obsidian/deps/`
  or `04_database_tools/dbeaver/` for a matching file you may have missed.
- If it's a CLI utility dependency: check `06_utilities/deb-packages/` again.
- If truly absent from the kit, this must be re-collected on the online VM and the kit
  re-transferred — it cannot be fixed on the offline server itself.

## SQL Server container exits immediately after `docker run`

Check the logs:
```
docker logs sqlserver
```
Common causes shown in the log:
- **"ACCEPT_EULA and MSSQL_SA_PASSWORD are required"** — you forgot one of those
  environment variables in the `docker run` command.
- **"Password validation failed"** — `MSSQL_SA_PASSWORD` doesn't meet complexity rules
  (needs 8+ characters, upper, lower, digit, symbol).
- **"error: pathspec... /var/opt/mssql"** or permission errors — the mounted volume has
  wrong ownership; try removing and recreating the named volume (only if no data exists
  yet — this destroys any data in it):
  ```
  docker volume rm mssql_data
  ```

## PostgreSQL container exits immediately after `docker run`

Check the logs:
```
docker logs postgres
```
Common cause: `POSTGRES_PASSWORD` environment variable missing — PostgreSQL refuses to
start without it on first run.

## DBeaver asks to "Download driver files" when testing a connection

This requires internet and will fail offline. The SQL Server / PostgreSQL JDBC drivers
must already be present in DBeaver's driver cache. If missing:
1. On the *online* VM, open DBeaver, let it download the driver once, then copy
   `~/.local/share/DBeaverData/drivers/` from the online machine to the same path on the
   offline server before connecting.
2. This is a one-time setup step — once copied, DBeaver will not ask again for that driver.

## Portainer web page won't load at `https://<server-ip>:9443`

1. Confirm the container is running: `docker ps` — look for a container named `portainer`.
2. Confirm the port is published: `docker port portainer` should show `9443/tcp`.
3. Confirm no firewall is blocking the port: `sudo ss -tlnp | grep 9443`.
4. Check container logs: `docker logs portainer`.

## Obsidian won't launch / crashes immediately

Usually a missing GTK/Electron dependency. Re-run:
```
bash 07_install_scripts/install_obsidian.sh
```
and check the output for any `dpkg` errors — every dependency `.deb` should already be in
`05_documentation_tools/obsidian/deps/`. If a specific `.so` library error appears in the
terminal when running `obsidian` directly, that library's package is likely missing from
`deps/` and must be re-collected on the online VM.

## xrdp installed but Windows Remote Desktop won't connect

1. Confirm the service is running: `sudo systemctl status xrdp --no-pager`.
2. Confirm it's listening: `sudo ss -tlnp | grep 3389` — should show `xrdp`.
3. Check for a firewall blocking port 3389: `sudo ufw status` (if `ufw` is in use) or
   check `nftables`/`iptables` rules with your network admin.
4. Confirm you're using the server's correct IP: `hostname -I` on the server itself.

## xrdp connects but shows a blank/black screen or crashes immediately

This is a known issue with GNOME Shell specifically — see the GNOME note in
`XRDP_GUIDE.md`. Try selecting an alternate lighter session at the login screen if one is
offered. XFCE and KDE Plasma do not have this problem.

## `verify_everything.sh` reports failures

The output tells you exactly which check failed (Docker, Portainer, an image, a tool,
disk space, RAM, or networking). Fix that one item using the matching section above, then
re-run:
```
bash 07_install_scripts/verify_everything.sh
```
