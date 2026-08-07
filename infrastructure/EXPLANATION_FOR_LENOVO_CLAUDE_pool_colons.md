# Re: the 58 zero-byte files in 01_APT_Repository/pool/

Your diagnosis is correct — confirmed from the source side. Those 58 files are exactly
the Debian packages whose filename contains a literal `:` (the "epoch" version prefix,
e.g. `docker-ce-cli_5:29.6.1-1~debian.13~trixie_amd64.deb`, `libcap2_1:2.75-...`, etc.).
Windows NTFS cannot represent a colon in a filename — it's a reserved character (used for
drive letters). This isn't a copy-method bug; it's a hard filesystem incompatibility.

Worth knowing the history: this exact character hit us once already, from the *other*
direction, building the pool in the first place. `apt-get download` on the real Linux
build machine initially saved some of these as `%3a` (percent-encoded) instead of a real
colon, which broke the Linux-side `dpkg-scanpackages` index generation — Debian package
filenames need the literal `:`. That got fixed by renaming to the real colon form, which
is completely valid on Linux (the actual target — a Debian offline server), just
fundamentally incompatible with being checked out as loose files in a Windows-hosted git
working tree. So the pool as it exists is *correct for its intended target*, not broken —
it just can't live as raw files here.

## Three ways to resolve it — pick one, don't guess

**1. Store the pool as a single archive blob, not loose files.**
A `.tar.gz` (or `.zip`) of the pool is just one opaque file with a normal name — tar/zip
as *formats* don't care that an internal entry name contains a colon, only the OS
filesystem does when something tries to extract it raw. This can sit in the git repo (or
git LFS, given its size) as `pool.tar.gz`, and only gets extracted on an actual Linux
machine (a build step, a CI runner, or directly on the target Debian host at install
time) — never extracted on Windows.

**2. Treat the pool as a generated build artifact, not committed source.**
Don't store the `.deb` files in git at all. Store the *build script* instead (the
`apt-get download <package list>` + `dpkg-scanpackages` process used to generate the
pool originally — small, text, entirely git-friendly) and regenerate the actual pool
fresh on a Linux build machine each release cycle. This is the more "proper" software
engineering answer — it's the same reasoning you'd apply to not committing `node_modules`
or compiled binaries. The generated pool would then get attached as a release artifact
(e.g. a GitHub Release binary attachment) rather than living in the git tree.

**3. Keep it exactly as-is on the source-of-truth Linux machine, reference it from there.**
Don't try to bring the raw pool into this Windows-hosted repo at all — the online VM
already has a verified-intact, checksummed copy. The repo could just document where the
authoritative copy lives and how to regenerate/fetch it, rather than solving the
Windows-storage problem at all.

My instinct: **option 2** is architecturally the cleanest fit for a proper GitHub project
(matches the "release artifact vs. committed source" distinction from the architecture
proposal in `docs/`), but that's a real decision for you and the user to make together —
it affects how releases get built going forward, not just how to unblock this one copy.
Don't just pick one and run — ask first, this is exactly the kind of structural call the
handoff prompt already told you to surface rather than assume.
