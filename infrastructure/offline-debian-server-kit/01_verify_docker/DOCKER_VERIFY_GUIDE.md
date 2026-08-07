# Docker Verification Guide

**Purpose:** Confirm Docker Engine is installed and healthy on the offline server.
**This guide does NOT install Docker.** Docker Engine is assumed to already be present.
If any check below fails, stop and see `08_documentation/TROUBLESHOOTING.md` — do not
attempt to `apt install docker` or download anything; this server has no internet.

You can run every check below by hand, or run the automated version instead:

```
bash 07_install_scripts/verify_docker.sh
```

The manual steps below are exactly what that script checks, in the same order, so you can
follow along or run them yourself if you prefer to see each command individually.

---

## Step 1 — Check the Docker Engine is installed and see its version

Command:
```
docker --version
```

Expected output (version numbers may differ, that is fine):
```
Docker version 29.6.1, build 8900f1d
```

**If you see "command not found"**: Docker is not installed or not on the PATH. Stop here
and escalate — this kit cannot fix that without internet access.

---

## Step 2 — Check the Docker background service is running

Command:
```
sudo systemctl status docker --no-pager
```

Expected output includes this line near the top:
```
Active: active (running)
```

**If you see "inactive (dead)" or "failed"**: try starting it and re-check:
```
sudo systemctl start docker
sudo systemctl status docker --no-pager
```

---

## Step 3 — Check Docker can talk to its own daemon and read basic system info

Command:
```
docker info
```

Expected output — look for these lines somewhere in the (long) output:
```
Server Version: 29.6.1
Storage Driver: overlayfs
```

**If this command hangs or errors with "Cannot connect to the Docker daemon"**: the Docker
service is not actually running correctly even if `systemctl status` looked fine. Go to
`08_documentation/TROUBLESHOOTING.md`.

---

## Step 4 — Check the Docker Compose plugin is available

Command:
```
docker compose version
```

Expected output:
```
Docker Compose version v5.3.0
```

(Any v2 or later version is fine. If this says "command not found", Compose was not
included with this Docker installation — flag this before continuing, later steps in this
kit rely on `docker compose`.)

---

## Step 5 — Check your user can run Docker without `sudo`

Command:
```
docker ps
```

Expected output (empty is fine — this just lists running containers):
```
CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES
```

**If you see "permission denied while trying to connect to the Docker daemon socket"**:
your user is not in the `docker` group. Fix with:
```
sudo usermod -aG docker $USER
```
Then log out and log back in (group membership only applies to new login sessions), and
re-run `docker ps`.

---

## Step 6 — Check available disk space for Docker images/volumes

Command:
```
df -h /var/lib/docker
```

Expected: at least 20 GB available in the `Avail` column. Docker images and database
volumes will be stored under this path.

---

## Step 7 — A real container test (do this AFTER loading images in Step 03)

`docker run hello-world` will not work offline because it has to download an image. Once
you have loaded the Portainer, SQL Server, or PostgreSQL images from `03_database_images/`
using `07_install_scripts/load_database_images.sh`, you can prove Docker actually runs
containers with:
```
docker run --rm postgres:<version-in-this-kit> postgres --version
```
Expected output: a line like `postgres (PostgreSQL) 16.x`.

This step is also covered automatically by `07_install_scripts/verify_everything.sh`.

---

## Summary — what "Docker is healthy" means

All of the following must be true before continuing to install anything else in this kit:

- [ ] `docker --version` prints a version number
- [ ] `systemctl status docker` shows `active (running)`
- [ ] `docker info` returns without error
- [ ] `docker compose version` prints a version number
- [ ] `docker ps` runs without `sudo` and without permission errors
- [ ] `/var/lib/docker` has at least 20 GB free
