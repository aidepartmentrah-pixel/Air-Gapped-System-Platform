# Real Manual Acceptance Test — Procedure

This is the one remaining item on Packager `P7`: proving that a Release
`rah package` actually finalizes can be copied to a genuinely air-gapped
machine, installed using only its own declared entrypoints, and made to
run — with nothing hand-patched along the way. Everything up to this point
(`rah plan`/`build`/`construct`/`package`/`validate`, 169/169 tests, all 56
automated `RC-*` rules) has been proven against real Docker builds and real
application repositories, but always from inside the Packager's own
container on the Windows engineering workstation. This test moves one step
further down the real chain: build → package → physically transfer →
install offline → verify.

This document is meant to be self-contained. If you are a Claude Code
session running on `or-stt` with no other context on this project, you
should be able to execute this end to end from this file alone, plus the
repository you just pulled.

## 1. Roles and where each phase runs

| Phase | Machine | What happens |
|---|---|---|
| 1. Package | `or-stt` (Online Debian VM) | Build the Packager container, clone/use the target application repo, run `rah package` to produce a finalized Release directory. |
| 2. Transfer | `or-stt` → `Offline-AirGapped-Simulator` | Revert the offline VM to the correct golden snapshot, copy the Release directory (and the `rah-packager` image) across the internal lab switch. |
| 3. Independent re-validate | `Offline-AirGapped-Simulator` | Run `rah validate` against the transferred copy — proves the bytes survived the transfer intact, with zero network dependency. |
| 4. Install | `Offline-AirGapped-Simulator` | Run the Release's own declared install entrypoint. |
| 5. Verify | `Offline-AirGapped-Simulator` | Run the Release's own declared verification entrypoint, confirm the required checks pass, confirm genuine offline operation. |
| 6. Restart check | `Offline-AirGapped-Simulator` | Restart the stack (or the VM) and re-confirm it comes back up unattended. |

This is a scoped-down **engineering acceptance test of Packager output**,
not a full hospital production deployment — it borrows the relevant checks
from the RAH Application Release & Deployment Standard's Deployment
Verification chapter (clean install, restart verification, offline runtime
verification) but does not attempt the full production rollout process.

## 2. Environment — read these first, don't guess

- `docs/infrastructure-reference/lab-environment-sanitized.md` — machine
  roles, network topology, known gotchas (including the `or-stt` SSH config
  bug: use `ssh -F /dev/null ...` or a per-host config, not plain `ssh`).
- `docs/infrastructure-reference/golden-baseline.md` — the snapshot to
  revert `Offline-AirGapped-Simulator` to before this test:

  ```
  GoldenSnapshot-WithRAHOIP
  ```

  (created 2026-07-16, RAH-OIP 1.0.0 fully installed and verified — Docker
  Engine, Compose plugin, curated APT repo, Portainer, DB images, etc.
  already present). **Do not** use `GoldenSnapshot-WithNetwork` (the older
  pre-Docker baseline) or the Hyper-V auto-generated checkpoint (predates
  network config entirely).
- If you need actual credentials, IPs, or SSH key paths, ask the user
  directly for the local (non-Git) lab reference — do not reconstruct them
  from memory or old conversation logs, and do not write them into any file
  in this repository.
- `or-stt` has pre-existing, unrelated containers (`or-tracking-offline-*`).
  Do not stop, remove, or otherwise touch them.

## 3. Which application to test first

**Use Indicator.** It has no database (`database.required: false`) and
every one of its Compose services declares its own `build:` context, so it
does not hit the one known, already-documented Packager gap: `RC-OFF-002`
("every Compose service's image has a local offline archive") currently
fails for any service that uses a **prebuilt** base image
(`image:` with no `build:` key — e.g. `mssql-server`, `postgres`), because
`P5`/`P6` only build and export images that have their own `build:` key in
Compose. Indicator is the one required acceptance app with no such image,
so it is the one most likely to pass the full offline install cleanly on
the first real attempt.

If you go on to test HCopilot, STT-SCHEDULE, or the Voice Project
afterward, **expect `RC-OFF-002` to fail at the `rah package`/`rah
validate` stage**, before you'd even get to the offline VM. That is
correct, expected behavior — it means the Compliance Report is doing its
job, not a bug to route around. Record it as a finding if it happens, don't
try to "fix" it by hand-copying a base image archive into the Release —
that would defeat the point of the test.

## 4. Phase 1 — Package, on `or-stt`

```bash
git clone <indicator-repo-url-or-path> /tmp/indicator
cd /path/to/Air-Gapped-System-Platform
docker build -t rah-packager packager/

# rah init, if this repo has never been packaged from this checkout before
docker run --rm \
  -v /tmp/indicator:/repo \
  rah-packager init --project /repo --name "Indicator"

# rah package: real Docker builds + all 56 RC-* rules + checksums +
# Compliance Report + atomic finalization, in one step
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp/indicator:/repo \
  -v /tmp/rah-output:/output \
  rah-packager package --project /repo --output /output --increment patch
```

Read the single JSON envelope `rah package` prints to stdout.
`result: "success"` means a finalized Release directory now exists under
`/tmp/rah-output/` (named `Indicator_Release_<version>` per
`release-layout.yaml`). `result: "error"` means it stopped cleanly with a
structured `PKG-*` error and produced no finalized output — read the error,
record it as a finding (section 7), and stop; do not hand-patch the Release
and continue.

If any engineering-answers gap comes up (`rah package` calling into `rah
plan`/`construct` internally needs `.rah/engineering-answers.json` to
exist and be fresh), run `rah prepare-answers` / `rah validate-answers`
first, the same way earlier slices did — see
`docs/development/Period A — Independent Product Development; Packager/2. Initial Slicing Task Table.md`
for worked examples against both HCopilot and Indicator.

Also export the Packager image itself, since the offline VM cannot pull it:

```bash
docker save rah-packager:latest -o /tmp/rah-output/rah-packager-image.tar
```

## 5. Phase 2 — Transfer, `or-stt` → `Offline-AirGapped-Simulator`

1. On the Legion (Hyper-V host), revert `Offline-AirGapped-Simulator` to
   the `GoldenSnapshot-WithRAHOIP` checkpoint (see section 2). Start it.
2. Confirm it has no route to the internet — this is the one property the
   whole test exists to protect. A quick `curl` to any public host from
   inside the VM should fail/time out.
3. Copy the finalized Release directory and the saved Packager image
   across the internal lab switch (`scp -F /dev/null`, or whatever transfer
   mechanism the lab reference documents):

   ```bash
   scp -F /dev/null -r /tmp/rah-output/Indicator_Release_<version> \
     <offline-vm-user>@<offline-vm-ip>:/home/<offline-vm-user>/
   scp -F /dev/null /tmp/rah-output/rah-packager-image.tar \
     <offline-vm-user>@<offline-vm-ip>:/home/<offline-vm-user>/
   ```

Do this over the internal switch only — the whole point is that this
transfer is the *only* path the bits take to reach the air-gapped side.

## 6. Phase 3 — Independent re-validate, on `Offline-AirGapped-Simulator`

```bash
docker load -i ~/rah-packager-image.tar

docker run --rm \
  -v ~/Indicator_Release_<version>:/release:ro \
  rah-packager validate --release /release
```

Expect `overall_result: PASS` and zero `checksum_mismatches`. This is the
step that actually proves something the automated test suite up to now
never could: that the bytes as installed on the genuinely air-gapped
machine are identical to the bytes `rah package` produced, with no network
transport involved in verifying that fact. If this fails, stop and record
it — do not proceed to install a Release that failed its own integrity
check.

## 7. Phase 4 — Install

Read `release.yaml` inside the transferred Release directory. Do not
hardcode the script name — the Contract's whole point is that the Platform
(and this test) discovers it from the manifest:

```bash
cat ~/Indicator_Release_<version>/release.yaml
```

Find `deployment.entrypoints.install` (a path relative to `scripts/`) and
`deployment.canonical_path` (must be `/opt/rah/apps/<slug>` per the
Contract). Run the declared install entrypoint from inside the Release
directory, e.g.:

```bash
cd ~/Indicator_Release_<version>
sudo bash scripts/<value-of-deployment.entrypoints.install>
```

Record exit code and full output. A non-zero exit or a crash is a real
finding, not something to route around.

## 8. Phase 5 — Verify

Same discovery approach — read `verification.entrypoint` and
`verification.required_checks` from `release.yaml`, then:

```bash
sudo bash scripts/<value-of-verification.entrypoint>
```

Separately, by hand, confirm the application actually works: the
containers are up (`docker compose ps` from the deployed
`compose_project_name`), and the app is reachable on its expected port from
inside the VM (`curl localhost:<port>` or a browser over `xrdp`). This is
the one step no automated `RC-*` rule can cover — the Contract validates
that a verification entrypoint *exists and is executable*, not that the
application is actually usable.

## 9. Phase 6 — Restart verification

Restart the stack (`docker compose restart`, or a full VM reboot for a
stronger proof) and re-run the same reachability check from Phase 5,
unattended — no re-running the install script. This is the standard
"does it survive a restart with no operator intervention" check from the
Deployment Standard, scoped down to what's relevant for a Packager-built
Release specifically.

## 10. What NOT to do

- Don't edit anything inside the transferred Release directory to make a
  failing step pass. If something is wrong, the Release Contract or the
  Packager has a real gap — that's exactly what this test is for.
- Don't give the offline VM a temporary route to the internet to work
  around a missing dependency. That would invalidate the one property this
  test exists to prove.
- Don't touch `or-stt`'s pre-existing `or-tracking-offline-*` containers.
- Don't commit anything to Git without asking first — this is a working
  discipline for this whole repository, not specific to this test.
- Don't leave the offline VM in a modified state as the new implicit
  baseline. When done, either revert it back to `GoldenSnapshot-WithRAHOIP`
  or explicitly tell the user you left it installed and why.

## 11. Where to write results

Append your results directly to the existing Testing Record in
`docs/development/Period A — Independent Product Development; Packager/2. Initial Slicing Task Table.md`,
under the `## P7 — Automated Portion Done` section, in the placeholder
subsection titled `### P7 — Real Manual Acceptance Test — Results` (already
scaffolded there, right after the "Not yet done" paragraph). Use the same
table format already established in that document's own
"Testing Memory for Every Slice" convention:

```
| Test ID | Test | Environment | Expected | Observed | Status |
|---|---|---|---|---|---|
| P7-RM-01 | rah package (Indicator) on or-stt | or-stt | PASS, finalized Release produced | ... | ... |
| P7-RM-02 | rah validate on transferred copy | Offline-AirGapped-Simulator | PASS, 0 checksum_mismatches | ... | ... |
| P7-RM-03 | Fresh install via declared entrypoint | Offline-AirGapped-Simulator | Exit 0, app reachable | ... | ... |
| P7-RM-04 | Declared verification entrypoint | Offline-AirGapped-Simulator | All required_checks pass | ... | ... |
| P7-RM-05 | Restart verification | Offline-AirGapped-Simulator | App reachable after restart, no manual steps | ... | ... |
```

Add a `Problems Discovered` paragraph underneath, same style as every other
slice's writeup in that document — plain prose, one real finding per
paragraph, root cause not just symptom. Report real results only: if a
phase wasn't reached because an earlier one failed, say so and mark later
rows `NOT RUN`, don't guess what they would have shown.

Do not commit the edited file. Leave it modified on disk on `or-stt`; the
user will pull the results back and decide what to commit.
