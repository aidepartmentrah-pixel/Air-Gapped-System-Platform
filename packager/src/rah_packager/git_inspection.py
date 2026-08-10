"""Git facts — the "Git" category of P2's `ProjectInspectionResult`
(docs/development/.../1. Initial GPT Proposal.md, P2: branch, commit, tag,
clean/dirty state).

Shells out to the real `git` binary rather than a Python Git library —
the Packager only needs a handful of read-only plumbing/porcelain
commands, and this way local dev (pytest against the host's `git`) and
the container runtime (the `git` installed in the Dockerfile) run the
exact same code path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from rah_packager.errors import GitInspectionError


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
    )


def _run_git_or_raise(repo_path: Path, *args: str) -> str:
    result = _run_git(repo_path, *args)
    if result.returncode != 0:
        raise GitInspectionError(
            f"`git {' '.join(args)}` failed in {repo_path}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _current_tag(repo_path: Path) -> str | None:
    """None if HEAD has no exact-match tag — that's a normal, expected
    outcome (most commits aren't tagged), not a failure.
    """
    result = _run_git(repo_path, "describe", "--tags", "--exact-match", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _remote_url(repo_path: Path) -> str | None:
    """None if no `origin` remote is configured — a normal, valid state
    for a local-only repository, not a failure. Needed by P6's Release
    Manifest `source.repository` field; P2 didn't need it, so it wasn't
    captured until now.
    """
    result = _run_git(repo_path, "config", "--get", "remote.origin.url")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def inspect_git(repo_path: str | Path) -> dict:
    """Assumes `repo_path` is already a confirmed Git repository (P1's
    `.git`-exists check). Raises GitInspectionError if `git` plumbing
    fails regardless — e.g. a repo with no commits yet, so `HEAD` doesn't
    resolve to anything.
    """
    path = Path(repo_path)

    branch = _run_git_or_raise(path, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _run_git_or_raise(path, "rev-parse", "HEAD")
    tag = _current_tag(path)
    # .rah/ is the Packager's own bookkeeping (project-state.json,
    # engineering-answers.json, ...), not application source — excluded so
    # writing into it (e.g. `rah init`, `rah prepare-answers`) doesn't
    # immediately flip an otherwise-clean repo to "dirty" on the very next
    # inspect. Real bug this fixes: P3 staleness fingerprints would never
    # match right after `prepare-answers` wrote its own output file.
    status = _run_git_or_raise(path, "status", "--porcelain", "--", ".", ":!.rah")

    return {
        "branch": branch,
        "commit": commit,
        "tag": tag,
        "state": "dirty" if status else "clean",
        "remote_url": _remote_url(path),
    }
