# Why This Project Needs a Curated APT Repository

Short version: **the target machines have no internet, and `apt` needs a
package source to install anything at all.** The curated repository is that
source, built once, shipped as data, not fetched at install time.

---

## The problem

Every offline Debian host this project touches — the Offline Validation VM,
and eventually the real hospital servers — is deliberately air-gapped. No
internet access, on purpose, permanently.

But installing Docker, Docker Compose, Portainer, DBeaver, Obsidian, xrdp,
and basic CLI tools (git, curl, wget, tmux, etc.) normally means running
`apt install <package>`, and `apt` normally fetches packages and dependency
metadata from Debian's public servers over the internet. On an air-gapped
machine, that fails immediately — there's nothing to fetch from.

So before any application, before the Offline Installation Platform itself
can even run, the target Debian machine needs a way to install ordinary
Debian packages **without the internet**. That's the entire reason this
module exists.

## What the curated repository actually is

Not a list of files someone picked by hand. It's a **real APT repository** —
the same format Debian's own servers use (a `Packages` index plus a `pool/`
of `.deb` files) — just small and self-contained instead of the size of all
of Debian. It contains only what RAH-OIP actually needs: Docker Engine,
Docker Compose, the database/tooling containers' host dependencies, and
supporting utilities — roughly 312 packages total.

During installation, the target machine's `apt` is pointed at this local
repository as its *only* source. From `apt`'s point of view, nothing is
different from a normal internet install — it still resolves dependencies
itself, using its own real solver. The only thing that changed is *where*
the packages come from.

## Why not just hand-copy the packages we think we need

We tried that first, and it broke, twice, in ways worth remembering:

- Manually walking `apt-cache depends --recurse` **missed real dependencies**
  entirely in one pass (Obsidian needed two packages the manual list didn't
  catch), and separately pulled in **two packages that conflict with each
  other** in another pass (`opensysusers` vs `systemd-standalone-sysusers`) —
  a graph-traversal-by-hand mistake, not something a real dependency solver
  would ever do.
- `apt-get install -s` (simulate mode) doesn't catch this — it only checks
  that the dependency graph is theoretically consistent, not that the actual
  files exist and are named correctly.

The fix wasn't a better manual list. It was **stop being the dependency
solver ourselves** — build a real repository (`dpkg-scanpackages` generates
the proper index), so the target's own `apt`, the same trusted tool Debian
itself relies on, does the resolving. That's the only way to get the
guarantee that "this set of packages actually installs cleanly together."

## What it's used for in this project, specifically

It's the install-time backing for `install_everything.sh` /
`verify_everything.sh` in the RAH-OIP Infrastructure Release
(`infrastructure/` in this repo). Those scripts are what turn a blank
Debian 13 machine into one that can actually run:

```
Docker Engine + Compose   → everything else in this project needs this
Portainer                 → container visibility/management
PostgreSQL / SQL Server   → database platforms applications use
DBeaver                   → operator-facing database administration
Obsidian                  → operational documentation viewer
xrdp                      → remote desktop access to the machine
git, curl, wget, tmux...  → ordinary admin tooling
```

Every layer above this depends on it existing first:

```
Curated APT repository
        ↓
Docker installed on the target Debian host
        ↓
Offline Installation Platform can run (it needs Docker + Postgres itself)
        ↓
Application Releases (HCAT, STT-SCHEDULE, ...) can be installed through it
```

Without this module, there is no way to get from "blank offline Debian box"
to "Docker is running here" at all — not a missing convenience, a hard
blocker.

## Why it's a separate, slightly awkward thing to store in this repo

The repository lives as data (a `pool/` of `.deb` files), not code, and it's
large (~377MB uncompressed). It's currently a live, unresolved question how
it best gets stored here — some of the real Debian package filenames contain
characters (a literal `:` from an "epoch" version prefix, e.g.
`docker-ce-cli_5:29.6.1-...`) that Windows' filesystem cannot represent at
all, which is why extracting it directly onto this Windows-hosted repo has
been failing. That's a storage-format problem to solve, not a reason the
module itself is optional — the Infrastructure Release already built,
shipped, and validated it successfully on the actual Linux target where this
constraint doesn't exist.
