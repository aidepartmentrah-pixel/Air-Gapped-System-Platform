# Packager Responsibility Boundaries — Who Actually Does What

Grounded in Stage 2's accepted "Hybrid Human/Claude + deterministic tooling"
resolution, sharpened using real evidence from HCAT (`Patient_Feedback`) and
Voice Project (`voice-project_Deployment`) — both already have hand-built
`release/` folders that prove this division works in practice, not just in
theory. Written because "the Packager will have to deal differently with
each project" sounds alarming until you see that the differences never
actually live inside the Packager's own code.

## The short version

Four things share the work of turning a heterogeneous application into a
standardized Release. Only one of them is the Packager, and its job is
deliberately the most boring one.

```
Docker           absorbs stack/language differences (Python vs Node vs
                 whatever) — the Packager never needs per-language logic,
                 it just runs `docker build` against whatever Dockerfile
                 the app already has.

Claude/human,    writes and maintains each app's own Dockerfile, decides
at app           what's baked into the image vs. not, structures the
development      app's own directories. Happens once, on that app's own
time              timeline, inside that app's own repo — NOT part of
                 packaging a release, already-existing fact by the time
                 the Packager runs.

Claude, at       (`rah prepare-answers`, P3 "Claude Knowledge Bridge")
packaging        answers narrow, structured questions the deterministic
time              inspector (P2) couldn't resolve from files alone —
                 e.g. "is this config value a secret." Tied to a Git
                 commit; goes stale if the repo changes. NOT redesigning
                 how the app containerizes — that already happened above.

The Packager     deterministic, generic, identical code path for every
itself            app: inspect → gate/preview (`rah plan`) → invoke
                 `docker build`/export using the app's existing
                 Dockerfile → assemble the fixed Release folder shape →
                 produce a new, immutable, versioned output directory.
```

## The load-bearing rule

**If anyone ever needs to write `if project == "HCAT"` inside the
Packager's own codebase, that's not a new app being supported — it's a
sign the Contract or the engineering-answers schema is incomplete.** The
fix in that moment is always a new generic field or inspection heuristic
that benefits every app, never a per-app class or branch. HCAT and Voice
Project — genuinely different stacks (Python/FastAPI+SQL Server+ML vs
Node.js+Python Whisper service+nginx+SQL Server) — already independently
converged on the identical `release/` folder shape by hand. What
differentiates them is entirely **data**: their own Dockerfiles, an
optional per-app lockfile-style declaration (HCAT's `models.lock.yaml` is
the real precedent), and the content of fixed-name lifecycle script slots
(`install_offline.sh`, `update_offline.sh`, `verify_installation.sh`,
backup/restore) — never bespoke Packager logic.

## Applied decision: everything bakes into Docker images

A direct corollary of "Docker absorbs the complexity": large app-specific
binary content (ML models included) is baked into the relevant Docker
image via ordinary `COPY`, not shipped as a separate declared Release
asset extracted at install time. No `assets/` concept in the Release
Contract. Accepted image sizes up to roughly 8GB where warranted.

**Why this is safe, not just convenient:** checked against real evidence —
`voice-project_Deployment/release/0.1.0/assets/whisper-model-medium.zip`
and the same file in `release/0.1.1/` are byte-identical (same SHA-256,
1.35GB) — the previously-used "separate asset" approach was already
re-shipping the full model, unchanged, in every release version, with zero
deduplication benefit actually being captured. Baking it into the image
instead costs nothing that wasn't already being paid, while removing an
entire bug class outright: the host-mount UID/ownership mismatch that
already broke pgAdmin and SQL Server in unrelated apps (see
`docs/development/application-validation-lessons.md`) cannot happen to
something that's baked into an image at build time, because there's no
runtime bind-mount to get the ownership of wrong.

This also directly serves automated testing (Period C, Jenkins): one
asset-handling path instead of two means fewer Contract validation rules,
fewer fixture types, and a more uniform "a Release always contains exactly
N Docker image tars, nothing else large" story to regression-test.

## Versioning: additive, not overwriting

Confirmed from real evidence, not just Stage 2's prose: `release/0.1.0/`
and `release/0.1.1/` coexist side by side in Voice Project's repo. Every
`rah package` run produces a new, immutable, versioned output directory —
it never overwrites a prior version's Release folder. (Stage 2's Threat 7
— "we have only one version at storage" — is about the *Platform's*
installed/active state on the target machine, a separate concern from the
Packager's build output.)
