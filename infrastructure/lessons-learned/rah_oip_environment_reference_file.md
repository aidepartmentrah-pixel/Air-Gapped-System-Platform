---
name: rah-oip-environment-reference-file
description: "Where to find current IPs, credentials, SSH connection methods, and known gotchas for the RAH-OIP lab's online/offline VMs and Legion workstation"
metadata: 
  node_type: memory
  type: reference
  originSessionId: b1cc9b3f-b4e9-4090-91ab-06313ec5ffe3
---

`/home/orstt/RAH-OIP_LAB_ENVIRONMENT_REFERENCE.md` on this machine (the online VM) is the
living reference for the [[rah-oip-lab-topology]] setup: current/last-known IPs for the
Legion and Offline Validation VM, SSH key paths and the broken-`ssh_config` bypass
(`-F /dev/null`), the offline VM's login (`abbass`, sudo), the Golden Snapshot name to
revert to before validation runs, and which extracted CLI tools live in `/tmp` and need
re-extracting in a fresh session (they don't survive across sessions).

Read this file before attempting to SSH into either machine — IPs in particular (the
Legion's especially) drift as its Wi-Fi network changes, so always verify reachability
rather than trusting a remembered value.

**New Hyper-V checkpoint as of 2026-07-16: `GoldenSnapshot-WithRAHOIP`** — same clean
Debian 13 desktop as `GoldenSnapshot-WithNetwork`, but with RAH-OIP-1.0.0 fully installed
(Docker Engine + Compose, curated APT repo, Portainer, SQL Server/Postgres images loaded,
DBeaver, Obsidian, xrdp, CLI utilities) via `07_Installation/install_everything.sh`, then
verified clean via `08_Verification/verify_everything.sh` (all checks passed, internet
still unreachable). **Prefer this over `GoldenSnapshot-WithNetwork` for any future
application-release testing** (e.g. Voice Project) that expects Docker/RAH-OIP already
present — it skips re-running the ~10-minute RAH-OIP install every time.

**Gotcha hit installing RAH-OIP this session:** don't background the remote install with
`nohup ... & disown` over SSH and then close the SSH connection — the script makes many
sequential `sudo` calls relying on the primed credential cache (`sudo -S -v` once up
front), and detaching from the controlling terminal invalidates that cache before later
steps run, so the script dies partway (got through Docker, died on the xrdp step here).
Fix: run the installer as a **foreground** `ssh -tt` command kept alive for the whole
duration (use the Bash tool's own background-task support to not block locally, but keep
the remote SSH session itself attached/foreground) so the sudo ticket stays valid
throughout.

**Legion IP as of 2026-07-16: `172.31.0.1`** (was `170.70.32.79` as of 2026-07-09; both
prior recorded IPs were unreachable this session). Found it by checking OR-STT's own
default gateway (`ip route show default`) and SSHing there directly — the Legion's Wi-Fi
adapter IP is reachable via ARP/routing through the Hyper-V Default Switch, so when the
last-known IP fails, checking the default gateway is a fast way to relocate it before
resorting to asking the user. Confirmed via `ssh -F /dev/null -i ~/.ssh/legion_key
it@172.31.0.1` returning hostname `LAPTOP-519QP5FI`.
