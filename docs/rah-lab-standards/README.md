# RAH Lab Standards — Reference Copies

This folder holds reference copies of the broader **RAH Lab** institutional
engineering standards — the hospital-wide documents that govern how RAH Lab
develops, releases, deploys, and operates software in general, not specific
to this repository.

They were added here so a Claude session working on `Air-Gapped-System-Platform`
can consult them directly instead of relying on them being pasted into a
conversation each time. This follows the same "git repo = development
memory" principle already used elsewhere in this project (see
`docs/development/2. GitHub Based Memory Theory-Development Notes.md`).

## Relationship to this repository

This is important context, not just filler: the documents in this folder —
especially **6. RAH Application Engineering Playbook** — describe the
**manual, prompt-driven process** RAH Lab currently uses to take a hospital
application from source code to a qualified offline release. That playbook
is literally four sequential prompts a human hands to Claude by hand:
Database Deployment Engineering → Application Dockerization → Application
Release Engineering → Offline Release Qualification.

**The Packager and Platform being built in this repository (`packager/`,
`platform/`, see `docs/development/CURRENT.md`) are software automating
that same lifecycle**, not a separate concern. The Release Contract
(`contracts/1.0/`), the Packager's slices (P0–P7), and the Platform's
slices (PL0–PL9) are, in effect, this project's attempt to turn the manual
4-prompt playbook into a deterministic, testable, repeatable tool — the
same reason the Packager's error categories, offline-dependency checks
(`RC-OFF-*`), and validation rules keep tracing back to concerns these
documents already named by hand (undeclared CDN dependencies, placeholder
passwords, persistent-vs-replaceable state, etc.).

When implementing a Packager or Platform slice and something is ambiguous,
these documents are the authoritative source for *why* a requirement
exists — the architecture docs under `docs/architecture/` define *what*
this specific project decided to build; these standards define the
*institutional* requirements that decision is answerable to.

## What is deliberately NOT here

**`8. RAH-OIP Lab Environment Reference.md` is intentionally excluded.**
It contains real credentials (a live password, SSH key paths) for the lab
environment, and its own header explicitly warns it is "not a doc to paste
elsewhere." This repository already made that exact call once before —
see `docs/infrastructure-reference/lab-environment-sanitized.md`, which is
the credential-free companion to that same document. If a future session
needs the real lab environment reference, it should be requested directly
from the engineer, never reconstructed from memory or committed here.

## Contents

1. `1. RAH Lab Operator Manual.md` — how approved releases are operated,
   installed, updated, and maintained in production.
2. `2. RAH Software Engineering Standard.md` — how applications must be
   engineered to be RAH-deployable (Docker, database, source control,
   release-engineering readiness).
3. `3. RAH Infrastructure Architecture.md` — the online/offline environment
   model, infrastructure roles, and shared services.
4. `4. RAH Model Registry & Release Protocol.md` — how ML model artifacts
   are versioned and delivered offline.
5. `5. RAH Application Release & Deployment Standard.md` — the required
   behavior of an Application Release: install, update, persistence,
   verification, compliance.
6. `6. RAH Application Engineering Playbook.md` — the four-prompt manual
   pipeline (database → Dockerization → release engineering → offline
   qualification) this project's Packager/Platform automate.
7. `7. RAH Offline Infrastructure Platform Standard.md` — how RAH-OIP
   itself (the underlying Debian platform) is engineered, validated, and
   published as versioned Infrastructure Releases.
