You're starting a new project on a Windows 11 Lenovo workstation: turning an existing
air-gapped-hospital-deployment DVD kit into a proper GitHub-hosted project — the "RAH
Offline Installation Platform." This file (and everything alongside it in this exported
folder) is your starting material, handed off from a separate Claude session that spent
weeks building and validating the underlying kit on a lab VM. Read `README.md` in this
same folder first — it explains what every subfolder is and flags the one recurring bug
pattern (non-root container UID vs. root-owned host-mounted directories) worth designing
around from day one.

**What exists so far, and why it's not yet "the platform":**
- `offline-debian-server-kit/` — a working, repeatedly-validated DVD kit: Docker,
  Portainer, SQL Server/Postgres images, DBeaver, xrdp, CLI utilities, all installable
  offline via shell scripts. This is infrastructure only — no UI, no install orchestration
  beyond running scripts by hand.
- `rah-oip-releases/` — a more disciplined, versioned reshaping of the same idea (real
  curated APT repo instead of hand-picked `.deb`s, a manifest, a compatibility matrix, a
  validation report format) — built once, following the proposal in
  `docs/RAH-OIP_Architecture_Proposal.md`, but not yet re-validated the way the flat kit
  was.
- Neither of these has any UI. Both assume an operator manually running shell scripts,
  editing `.env` files by hand, and hunting for free ports themselves.

**What the user actually wants now (their own words, lightly cleaned up):** a platform —
a webpage/control panel — that sits on top of whatever the release-folder format becomes,
and makes installing, updating, and tracking custom hospital applications easy through a
UI instead of raw shell scripts. Concretely, from their planning notes (there should be a
file describing this in more detail alongside this one, or ask them directly if not):
- Guided install: pick install directory, pick a port (with free-port detection/testing
  built in), fill in credentials through a form instead of `nano`-ing a `.env` file.
- A dashboard showing what's installed, what version, whether it's up to date, with
  install/update buttons that appear based on that status.
- A "Linux Operations" tab for installing the base infrastructure pieces (Docker, DBeaver,
  Obsidian, etc.) — status-only, no update tracking needed there.
- Explicit non-goals, stated by the user: **not** a version control system, **not** a
  Docker management UI replacement (not "another Portainer"), **not** a second competing
  definition of what a release is. It consumes a release format; it doesn't invent one.
- The user has already reasoned through this at a conceptual level (see their own
  planning doc, likely titled something like "Idea Definition ; Is it Worth It.md" — ask
  them for it if it isn't already sitting next to this file) and reached the conclusion
  that a **stable, machine-readable contract between the release-folder format and the
  platform** is the load-bearing piece — without it, a platform can't safely assume
  anything about folder shape, script names, or config conventions across releases
  written at different times by different Claude sessions.

**Your first job is NOT to start writing platform code.** Read what's here, read the
user's own planning notes if they share them, and help them work through:
1. What that release/platform contract should actually look like (this is the open
   question their own notes end on — "Stage 1: Identification and Resolution of
   Existential Threats" was the planned next step, not yet done).
2. Whether `rah-oip-releases/`'s existing manifest/compatibility-matrix shape is a good
   starting point for that contract, or whether it needs to change to serve a platform
   consumer rather than a human DVD-builder.
3. How to structure this as an actual GitHub repo — the binary content in both existing
   folders (Docker image tars, `.deb`/`.jar` files, several GB total) is not git-friendly
   as committed content; work out with the user whether that means `.gitignore` +
   fetch/build-at-release-time, Git LFS, or something else, before just committing
   everything as-is.

Ask the user clarifying questions before making structural decisions — this is exactly
the kind of judgment call (contract shape, repo layout, scope boundaries) their own notes
say they want to make deliberately, not have assumed for them.
