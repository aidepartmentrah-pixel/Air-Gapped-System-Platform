# RAH Lab Environment Reference (Sanitized)

This is a sanitized companion to a local-only lab environment reference that
also contains real credentials and SSH key paths. That original file is
**not** in this repository and never will be — it stays on the machine where
it was written, treated like a credentials file.

This document keeps everything from it that is useful for development and
contains no secrets: machine roles, topology, software versions, and known
operational gotchas. If you need actual connection credentials, ask for the
local reference directly — don't reconstruct it from memory or old
conversation logs.

---

## 1. Machine Roles

### Windows 11 Lenovo Legion — Engineering Workstation

- Hosts both VMs below via Hyper-V.
- Also where application Docker images get built (Docker Desktop).
- SSH access is key-based (not password-based).
- Its own network address is **not stable** (DHCP/Wi-Fi) — always verify the
  current address before connecting rather than reusing a cached one.

### Online Debian VM — "or-stt" (Release Engineering Machine)

- Where release engineering work happens.
- Two network interfaces: one on the internal lab switch (talks to the
  offline VM), one with normal internet access.
- Docker installed from Docker's official apt repository (not Debian's
  `docker.io` package).
- **Known bug:** the system-wide SSH client config on this VM has an invalid
  line (a server-side directive incorrectly placed in the client config)
  that makes the default `ssh` invocation refuse to run. Workaround: bypass
  the system config explicitly (e.g. `ssh -F /dev/null ...`) or use a
  per-host config file. This can't be fixed in place without root, which
  isn't available in-session.
- **Pre-existing unrelated workload — do not touch:** several containers
  belonging to prior, unrelated work already run on this VM. Don't assume a
  clean Docker host.

### Offline Validation VM — "Offline-AirGapped-Simulator"

- Debian 13 (trixie), amd64, full desktop install.
- Static internal IP, persistently configured (survives reboot), no gateway
  configured — genuinely no internet access (repeatedly confirmed).
- Sudo-enabled user, password required each time (no passwordless sudo).
- SSH reachable directly on the internal lab network.

---

## 2. Network Topology

Two Hyper-V virtual switches on the Legion:

- **Default Switch** — Hyper-V's NAT switch, gives internet access.
- **Offline-Lab** — internal-only switch connecting the Online Debian VM and
  the Offline Validation VM on a private `/24` network. This is the boundary
  that makes the offline VM genuinely air-gapped: it only has an interface
  on this switch, nothing routes it anywhere else.

The Online Debian VM straddles both switches (internal + internet); the
Offline Validation VM is only ever on the internal switch.

---

## 3. Golden Snapshots

See `golden-baseline.md` in this same directory for the canonical reference.
Summary: there are two named Hyper-V checkpoints of the offline VM — a
pre-Docker baseline and a post-RAH-OIP baseline (the preferred one for
application/platform testing) — plus an auto-generated checkpoint that
predates network configuration and should not be used.

**General gotcha worth keeping in mind:** Hyper-V's automatic checkpoints can
predate manual configuration changes. Always verify what a checkpoint
actually contains before trusting it as a baseline; prefer an explicitly
named, deliberately taken checkpoint over an automatic one.

---

## 4. Software Versions in RAH-OIP 1.0.0

| Component | Version | Notes |
|---|---|---|
| Target OS | Debian 13 (trixie), amd64 | |
| Docker Engine | `5:29.6.1-1~debian.13~trixie` | From Docker's official repo |
| Docker Compose plugin | `5.3.1-1~debian.13~trixie` | |
| Docker Buildx plugin | `0.35.0-1~debian.13~trixie` | |
| containerd | `2.2.5-1~debian.13~trixie` | |
| Portainer CE | local tag `dd43259` | |
| SQL Server | local tag `2022-pinned` | Edition chosen at container runtime via `MSSQL_PID` (Express by default) |
| PostgreSQL | `16.14` | |
| DBeaver CE | `26.1.2` | Bundles its own JRE, no external deps |
| Obsidian | `1.12.7` | Needs two hand-built compatibility shims on Debian 13 (see lessons below) |
| xrdp | `0.10.1-3.1+deb13u1` | |
| xorgxrdp | `1:0.10.2-1` | Requires target already has an Xorg desktop |

Full package list (312 entries) is tracked in this repo's sibling
infrastructure-release repository, not duplicated here.

---

## 5. Key Lessons From Building RAH-OIP 1.0.0

These are non-secret engineering lessons worth keeping visible rather than
letting them live only in a private lab notebook.

1. **Hand-computed dependency closures are unreliable.** Manually walking
   `apt-cache depends --recurse` missed direct dependencies entirely in one
   pass, and separately pulled in two mutually-conflicting alternative
   packages in another. Fix: build a real curated local APT repository (with
   `dpkg-scanpackages`) so the target's own `apt` solver resolves
   dependencies — not a hand-computed list.
2. **`apt-get install -s` (simulate) does not catch file-path/fetch bugs** —
   it only validates the dependency graph. A real (non-simulated) install,
   or at minimum `--download-only`, is required to catch path/encoding bugs.
3. **`apt-get download` can produce percent-encoded filenames** (literal
   `%3a` for epoch colons) that break `dpkg-scanpackages`'s `Filename:` field
   unless renamed to their decoded form first.
4. **Flat-repo APT format requires `Packages`/`Packages.gz` at the
   repository root**, not inside the `pool/` subdirectory — `Filename:`
   entries are relative to the root.
5. **`--no-install-recommends` matters** — without it, `apt-get install`
   pulls in Recommends not present in the curated repo, causing a silent
   fallback to internet sources that won't be reachable in production.
6. **Debian's t64 transition renamed many packages** (e.g. `libgtk-3-0` →
   `libgtk-3-0t64`). Upstream non-Debian `.deb`s (like Obsidian's) built
   against the old names need a compatibility shim package on Debian 13.
7. **Don't background a long-running remote installer and detach the
   terminal** (e.g. `nohup ... & disown` then closing the SSH connection) if
   it depends on a primed `sudo` credential cache — detaching invalidates
   the cache before later steps run. Run it as a foreground command that
   stays connected for the whole duration instead.
8. **Hyper-V automatic checkpoints can predate manual config changes** —
   see the Golden Snapshots section above.

---

## 6. What's Deliberately Left Out

Removed from the original reference before this sanitized copy was written:

- Windows account credentials.
- SSH private key file paths.
- The offline VM's sudo/root password.
- Any command examples that embedded the above.

If you need any of this, it's in the local-only original — ask for it
directly rather than reconstructing it.
