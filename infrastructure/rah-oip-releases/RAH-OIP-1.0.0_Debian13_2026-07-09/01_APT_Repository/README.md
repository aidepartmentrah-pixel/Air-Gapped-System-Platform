# pool.tar.gz

The curated APT package pool (312 `.deb` files), archived as a single blob because ~58 of
the real Debian package filenames contain a literal `:` (the "epoch" version prefix,
e.g. `docker-ce-cli_5:29.6.1-...`) — a character Windows NTFS cannot represent in a
filename at all. See `../../../EXPLANATION_FOR_LENOVO_CLAUDE_pool_colons.md`
(`infrastructure/EXPLANATION_FOR_LENOVO_CLAUDE_pool_colons.md` from the repo root) for the
full story, including two alternative storage approaches that were considered but not
chosen — this archive-blob approach is a practical unblock, not yet confirmed as the
permanent answer.

**Never extract this on Windows** — it will fail or silently mangle those filenames.
Extract it only on a Linux machine (a build step, CI runner, or the actual Debian target)
at the point it's actually needed:

```bash
cd 01_APT_Repository
tar -xzf pool.tar.gz
```

This recreates `pool/` exactly as `dpkg-scanpackages` originally produced it, matching
the relative `Filename: pool/<name>.deb` paths already recorded in the `Packages` index
sitting alongside this archive — no other changes needed for `install_everything.sh` to
find everything it expects.

Verified before upload: extracts to exactly 312 files, zero corruption, from the
checksummed source copy on the online lab VM.
