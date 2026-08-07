# Validation Checklist — Offline Server Readiness Sign-off

Complete this checklist after running `07_install_scripts/install_everything.sh` and
`07_install_scripts/verify_everything.sh`. Keep a filled-in copy for records before
handing the server over for hospital application deployment.

Server hostname/IP: ______________________
Date completed: ______________________
Completed by: ______________________

## Integrity

- [ ] `sha256sum -c CHECKSUMS.txt` reports all `OK`

## Docker

- [ ] `docker --version` prints a version
- [ ] `systemctl status docker` shows `active (running)`
- [ ] `docker info` returns without error
- [ ] `docker compose version` prints a version
- [ ] `docker ps` runs without `sudo`
- [ ] At least 20 GB free under `/var/lib/docker`

## Portainer

- [ ] `docker ps` shows a container named `portainer` running
- [ ] `https://<server-ip>:9443` loads in a browser
- [ ] Admin account created and password recorded in a password manager

## Database images

- [ ] `docker images` shows `mcr.microsoft.com/mssql/server:2022-pinned`
- [ ] `docker images` shows `postgres:16.14`
- [ ] (If tested) a manually started SQL Server container logs
      "SQL Server is now ready for client connections"
- [ ] (If tested) a manually started PostgreSQL container logs
      "database system is ready to accept connections"

## Database tools

- [ ] `dbeaver-ce` launches successfully
- [ ] `obsidian` launches successfully

## CLI utilities

- [ ] `git`, `curl`, `wget`, `htop`, `nano`, `vim`, `rsync`, `zip`, `unzip`, `tmux`,
      `tree` all respond to `--version`/`--help`

## Remote desktop (xrdp)

- [ ] `sudo systemctl status xrdp` shows `active (running)`
- [ ] `dpkg -s xorgxrdp` shows `Status: install ok installed`
- [ ] A test RDP connection from a Windows machine (`mstsc`) to `<server-ip>:3389`
      successfully reaches your actual desktop session (not a blank/separate one)

## System resources

- [ ] `df -h /` shows at least 20 GB free
- [ ] `free -h` shows at least 4 GB total RAM

## Final automated check

- [ ] `bash 07_install_scripts/verify_everything.sh` exits with:
      `ALL CHECKS PASSED. Server is ready for hospital application release packages.`

## Sign-off

Once every box above is checked, this server is ready to receive an application's
release package (Dockerfiles, docker-compose.yml, database install scripts) produced by
the Dockerization prompts (2A for SQL Server projects, 2B for PostgreSQL projects).

Signed: ______________________   Date: ______________________
