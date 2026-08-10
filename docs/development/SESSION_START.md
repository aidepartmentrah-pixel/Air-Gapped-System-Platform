# Session Start — Read This First, Every Session

This document is phase-agnostic on purpose — it doesn't say what to build,
because that changes constantly. It says how to *find out* what to build,
regardless of whether the project is on Packager P1 or Platform PL4 or
Period C. Don't hardcode a specific slice/phase into this file; if you're
tempted to, that information belongs in `CURRENT.md` instead.

## 1. Read, in this order

1. **`docs/development/CURRENT.md`** — the front door. Says what phase,
   what period/track, what slice is active, what's blocked, what's next.
   This is the single source of truth for "where are we" — always correct
   because it gets updated as work happens, not written once and left
   stale.
2. Whatever period/slice plan file `CURRENT.md` points at for the active
   work (e.g. `Period A — Independent Product Development;
   Packager/1. Initial GPT Proposal.md` for the actual spec of a slice,
   and `2. Initial Slicing Task Table.md` for its live status).
3. If touching the Release Contract or anything that consumes it: the
   relevant `contracts/1.0/*` file directly, not a memory of what it
   contains — schemas and rule sets are exact, don't approximate them.
4. If a genuine design question comes up that isn't answered by the above:
   check `docs/decisions/` for a standalone record before assuming nothing
   exists — several non-obvious boundary questions are already answered
   there (e.g. `packager-responsibility-boundaries.md`).

## 2. How this project's documentation is organized — don't relitigate

- `docs/architecture/` — the frozen mental model of how the system works.
  Read to understand *why*. Don't edit casually; changes come from
  implementation evidence, not speculative redesign.
- `docs/development/` — the live tracker. `CURRENT.md` plus per-period
  plan files. Update this *as work happens*, not as an afterthought.
- `docs/decisions/` — standalone records that clarify/extend the frozen
  architecture without reopening it directly.
- A persistent cross-session memory system also exists and auto-loads
  into context (`MEMORY.md` and its linked files) — it holds durable
  decisions and working preferences, not project status. Trust it, but it
  points back at the real docs above for anything substantive; don't treat
  a memory summary as a substitute for reading the actual file it points
  to when precision matters.

## 3. Working discipline established on this project — keep it up

- **Build, then actually run it.** Don't report a slice complete on the
  strength of code that was written but never executed. The standard set
  by Packager P0: tests passing *and* every proof re-verified live against
  the real artifact (a real built container, a real repo, a real Docker
  Engine) — not mocked, not assumed.
- **One canonical home per piece of information.** Don't let the same
  status/table/decision exist in two files — that's already caused real
  drift once (a duplicated Master Development Matrix went out of sync
  before being consolidated). If information already has a home, update
  it there; don't create a second copy.
- **Keep status current as you go**, not as a separate cleanup task at the
  end. `CURRENT.md` and the relevant slice table should reflect reality at
  all times, not just when someone remembers to update them.
- **Match documentation effort to what's actually needed.** This project
  went through a phase of real process overhead (the user's own words:
  "I think we accidentally invented bureaucracy 😂") before correcting to
  "apply decisions directly to the canonical plan, don't spin up a
  separate review-record document for every review pass." Default to
  editing existing docs in place; only create a new standalone document
  when it has genuine standalone value.
- **Ask before git operations.** Never commit, push, or otherwise touch
  git state without the user asking first.
- **Never invent the full scope of an explicitly deferred design task.**
  If `CURRENT.md`'s "Future Design Tasks" section lists something as
  deliberately not designed yet (e.g. the Packager's `PKG-*` operational
  error-code namespace), don't design it inline while doing unrelated
  work — it was deferred on purpose.

## 4. First action

After reading the above: state in one or two sentences what the active
slice/task actually is per `CURRENT.md`, and confirm that understanding
before making changes — don't assume; `CURRENT.md` is kept accurate
specifically so this confirmation is fast, not so it can be skipped.
