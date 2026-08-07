---
name: rah-oip-lab-topology
description: The two-VM (online + offline) lab setup used to build and validate the RAH Offline Infrastructure Platform and hospital app releases before they reach the real air-gapped hospital server
metadata: 
  node_type: memory
  type: project
  originSessionId: b1cc9b3f-b4e9-4090-91ab-06313ec5ffe3
---

This machine (where Claude runs, hostname `or-stt`, Hyper-V VM name `OR-STT`) is the
**Online Debian VM / Release Engineering Machine**. It has internet access and is used to:
- Build the curated local APT repository and pull Docker images for the RAH-OIP platform.
- Pull hospital application release packages from the Windows engineering workstation
  ("the Legion") for testing.
- SSH into both the Legion and the Offline Validation VM to drive testing.

There is a second VM, the **Offline Validation VM** (Hyper-V name
`Offline-AirGapped-Simulator`), reachable at `10.10.10.2` on an internal-only Hyper-V
switch (`Offline-Lab`) with genuinely no internet access. It simulates the real,
production air-gapped hospital server. Debian 13 (trixie), user `abbass` (sudo).

**Why this two-VM setup exists:** the actual target is a real air-gapped hospital server
with zero internet access — testing changes directly on that real hardware is too risky.
So the workflow is: build/curate a release on the online VM (has internet) → transfer it
to the Offline Validation VM and run the exact install/verify scripts there, from a clean
snapshot, with network access genuinely cut off → only once that passes cleanly is the
same release copied to the real hospital server. This is standard build → staging-validate
→ prod-deploy discipline, adapted for an air-gapped target.

Both VMs are hosted via Hyper-V on a Windows 11 Lenovo ("the Legion"). Hospital
application release folders live on the Legion's filesystem (under
`C:\Users\it\Documents\...` — several separate GitHub project folders, each with its own
`release/` subfolder) and must be pulled from there, then relayed through this online VM
to the Offline Validation VM (the Legion cannot reach 10.10.10.2 directly — different
Hyper-V switch).

The Legion's Wi-Fi IP changes periodically (network changes) — always re-verify
reachability before assuming a cached IP still works.

Full connection details (current IPs, credentials, SSH key locations, known gotchas like
a broken `/etc/ssh/ssh_config` needing `-F /dev/null` bypass, and the ephemeral-`/tmp`
tools that need re-extracting each fresh session) are kept up to date in
[[rah-oip-environment-reference-file]] — read that file at the start of any session that
needs to actually connect to these machines, since exact values here would go stale fast.
