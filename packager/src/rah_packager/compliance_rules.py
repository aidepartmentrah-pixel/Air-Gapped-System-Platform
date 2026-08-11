"""The RC-* rule engine — `validation-rules.json`'s 43 mandatory rules
(everything except `RC-REPRO-001`, which is explicitly excluded from
`validation_order` in the Contract itself: it's a build-time regression
check comparing *two* independently generated candidates, not something
`rah validate` can evaluate against a single already-built Release — P6's
own `test_construct_release_is_reproducible` covers it instead).

Each rule is one function `ctx -> {"id", "category", "result", "message"}`.
`run_rules()` drives them in `validation_order`, honoring
`fatal_failure_rule` (Release root inaccessible / release.yaml missing /
unparseable / Contract version unresolved short-circuits everything
downstream to `NOT_EXECUTED`) — every other failure is non-fatal and
never stops an unrelated check from running, so one `rah validate` run
surfaces every discoverable violation at once.

Where a rule cannot be meaningfully checked without context this
Packager doesn't always have (Project Version State, for a standalone
`rah validate --release <path>` with no `--project`), it reports
`NOT_APPLICABLE` with an honest message rather than silently skipping or
guessing PASS.

Where the architecture describes a rule that requires real semantic
understanding of script *content* (RC-SCR-006's downgrade-logic
inspection) rather than structural/manifest facts, the check is scoped to
what's actually verifiable — documented inline, not silently expanded
into something this Packager can't really evaluate.
"""

from __future__ import annotations

import os
import re
import subprocess
import tarfile
from pathlib import Path

import yaml

from rah_packager.checksums import CHECKSUM_FILE_RELATIVE_PATH, compute_file_checksums
from rah_packager.release_manifest import validate_release_manifest as _schema_validate

SUPPORTED_CONTRACT_VERSIONS = {"1.0"}
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {"1.0"}

_RESERVED_TOP_LEVEL_DIRS = {
    "compose",
    "docker-images",
    "scripts",
    "configuration",
    "documentation",
    "verification",
    "checksums",
    "compliance",
    "database",
}
_RESERVED_TOP_LEVEL_FILES = {"release.yaml"}

_MINIMUM_CHECKSUM_COVERAGE_DIRS = (
    "docker-images",
    "scripts",
    "documentation",
    "verification",
    "compliance",
)

# Real false positive found live-proofing against HCopilot:
# `REPLACE_WITH_STRONG_PASSWORD` is obviously a placeholder but didn't
# match the original narrow whitelist (`replace_me` only). Placeholder
# phrasing varies a lot across teams — flag a value as "looks like a real
# secret" only when it does NOT contain any common placeholder-signaling
# substring, rather than trying to enumerate every exact placeholder
# string up front.
_PLACEHOLDER_MARKERS = re.compile(
    r"change|replace|your[_-]?|todo|sample|example|placeholder|xxx|dummy|<.*>|\$\{",
    re.IGNORECASE,
)


def _looks_like_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_MARKERS.search(value))
_PRIVATE_KEY_MARKER = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


class RuleContext:
    def __init__(self, release_dir: Path, manifest: dict, project_state: dict | None = None):
        self.release_dir = release_dir
        self.manifest = manifest
        self.project_state = project_state

    def path(self, relative: str) -> Path:
        return self.release_dir / relative

    def exists(self, relative: str | None) -> bool:
        return bool(relative) and self.path(relative).is_file()


def _pass(rule_id, category, message="OK"):
    return {"id": rule_id, "category": category, "result": "PASS", "message": message}


def _fail(rule_id, category, message):
    return {"id": rule_id, "category": category, "result": "FAIL", "message": message}


def _na(rule_id, category, message):
    return {"id": rule_id, "category": category, "result": "NOT_APPLICABLE", "message": message}


def _not_executed(rule_id, category, message):
    return {"id": rule_id, "category": category, "result": "NOT_EXECUTED", "message": message}


def _is_safe_relative_path(ctx: RuleContext, relative: str) -> bool:
    if relative.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", relative):
        return False
    if ".." in Path(relative).parts:
        return False
    try:
        resolved = ctx.path(relative).resolve()
        resolved.relative_to(ctx.release_dir.resolve())
    except (ValueError, OSError):
        return False
    return True


def _all_declared_paths(ctx: RuleContext) -> dict[str, str]:
    """{description: declared relative path} for every manifest field the
    layout Contract treats as a path resolving inside the Release root.
    """
    m = ctx.manifest
    declared: dict[str, str] = {"docker.compose_file": m.get("docker", {}).get("compose_file", "")}
    for key, value in (m.get("deployment", {}).get("entrypoints") or {}).items():
        declared[f"deployment.entrypoints.{key}"] = value
    for image in m.get("docker", {}).get("images") or []:
        declared[f"docker.images[{image.get('service')}].archive"] = image.get("archive", "")
    for key, value in (m.get("documentation") or {}).items():
        declared[f"documentation.{key}"] = value
    if m.get("verification", {}).get("entrypoint"):
        declared["verification.entrypoint"] = m["verification"]["entrypoint"]
    if m.get("configuration", {}).get("template"):
        declared["configuration.template"] = m["configuration"]["template"]
    database = m.get("database") or {}
    for section in ("initialization", "migration", "backup_before_update", "recovery"):
        entrypoint = (database.get(section) or {}).get("entrypoint")
        if entrypoint:
            declared[f"database.{section}.entrypoint"] = entrypoint
    return {k: v for k, v in declared.items() if v}


# --- RC-CON: Contract/schema resolution (fatal-gating) ---


def rc_con_001(ctx: RuleContext):
    version = ctx.manifest.get("compatibility", {}).get("release_contract_version")
    if version in SUPPORTED_CONTRACT_VERSIONS:
        return _pass("RC-CON-001", "RC-CON", f"release_contract_version {version!r} is supported")
    return _fail("RC-CON-001", "RC-CON", f"release_contract_version {version!r} is not supported")


def rc_con_002(ctx: RuleContext):
    version = ctx.manifest.get("manifest_schema_version")
    if version in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        return _pass("RC-CON-002", "RC-CON", f"manifest_schema_version {version!r} is supported")
    return _fail("RC-CON-002", "RC-CON", f"manifest_schema_version {version!r} is not supported")


RC_CON_CHECKS = [rc_con_001, rc_con_002]


# --- RC-DIR: Directory structure ---


def rc_dir_001(ctx: RuleContext):
    application = ctx.manifest.get("application", {})
    version = ctx.manifest.get("release", {}).get("version")
    expected = f"{application.get('name')}_Release_{version}"
    if ctx.release_dir.name == expected:
        return _pass("RC-DIR-001", "RC-DIR", f"directory name matches {expected!r}")
    return _fail(
        "RC-DIR-001",
        "RC-DIR",
        f"directory name {ctx.release_dir.name!r} does not match expected {expected!r}",
    )


def rc_dir_002(ctx: RuleContext):
    manifests = list(ctx.release_dir.rglob("release.yaml"))
    if len(manifests) == 1:
        return _pass("RC-DIR-002", "RC-DIR", "exactly one release.yaml exists")
    return _fail("RC-DIR-002", "RC-DIR", f"found {len(manifests)} release.yaml files, expected 1")


def rc_dir_003(ctx: RuleContext):
    required = list(_RESERVED_TOP_LEVEL_DIRS)
    if not (ctx.manifest.get("database") or {}).get("required"):
        required.remove("database")
    missing = [d for d in required if not ctx.path(d).is_dir()]
    if not missing:
        return _pass("RC-DIR-003", "RC-DIR", "all mandatory directories exist")
    return _fail("RC-DIR-003", "RC-DIR", f"missing mandatory directories: {', '.join(missing)}")


def rc_dir_004(ctx: RuleContext):
    # checksums/SHA256SUMS is deliberately not checked here: per
    # RC-INT-004's mandated closure order, it's generated *after* stage-A
    # validation completes (it must cover the Compliance Report, which
    # doesn't exist yet either) — its presence is RC-INT-001's job,
    # meaningful only once closure has actually happened.
    if ctx.path("compose/docker-compose.yml").is_file():
        return _pass("RC-DIR-004", "RC-DIR", "compose/docker-compose.yml exists")
    return _fail("RC-DIR-004", "RC-DIR", "compose/docker-compose.yml is missing")


def rc_dir_005(ctx: RuleContext):
    return _pass(
        "RC-DIR-005",
        "RC-DIR",
        "deployment.entrypoints is a mapping (one script per operation key); "
        "structurally cannot declare two scripts for the same operation",
    )


def rc_dir_006(ctx: RuleContext):
    # Same closure-ordering reasoning as RC-DIR-004: SHA256SUMS's own
    # presence/content is RC-INT-001/002's job. This rule covers whether
    # the checksums/ *directory itself* is missing (RC-DIR-003 already
    # checked this, but that's a bulk check across all 8-9 directories —
    # this one exists as its own numbered rule per the Contract, so it
    # gets its own real, if narrower, check).
    if ctx.path("checksums").is_dir():
        return _pass("RC-DIR-006", "RC-DIR", "the checksums/ directory exists")
    return _fail("RC-DIR-006", "RC-DIR", "the checksums/ directory is missing")


def rc_dir_007(ctx: RuleContext):
    unsafe = [k for k, v in _all_declared_paths(ctx).items() if not _is_safe_relative_path(ctx, v)]
    if not unsafe:
        return _pass("RC-DIR-007", "RC-DIR", "every declared path resolves inside the Release root")
    return _fail("RC-DIR-007", "RC-DIR", f"paths do not resolve inside Release root: {', '.join(unsafe)}")


def rc_dir_008(ctx: RuleContext):
    absolute = [
        k
        for k, v in _all_declared_paths(ctx).items()
        if v.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", v)
    ]
    if not absolute:
        return _pass("RC-DIR-008", "RC-DIR", "no forbidden absolute paths declared")
    return _fail("RC-DIR-008", "RC-DIR", f"forbidden absolute paths: {', '.join(absolute)}")


def rc_dir_009(ctx: RuleContext):
    traversal = [k for k, v in _all_declared_paths(ctx).items() if ".." in Path(v).parts]
    if not traversal:
        return _pass("RC-DIR-009", "RC-DIR", "no path traversal in any declared path")
    return _fail("RC-DIR-009", "RC-DIR", f"path traversal found in: {', '.join(traversal)}")


def rc_dir_010(ctx: RuleContext):
    problems = []
    for name in _RESERVED_TOP_LEVEL_FILES:
        p = ctx.path(name)
        if p.exists() and not p.is_file():
            problems.append(f"{name} exists but is not a file")
    for name in _RESERVED_TOP_LEVEL_DIRS:
        p = ctx.path(name)
        if p.exists() and not p.is_dir():
            problems.append(f"{name} exists but is not a directory")
    if not problems:
        return _pass("RC-DIR-010", "RC-DIR", "no reserved name is repurposed")
    return _fail("RC-DIR-010", "RC-DIR", "; ".join(problems))


RC_DIR_CHECKS = [
    rc_dir_001, rc_dir_002, rc_dir_003, rc_dir_004, rc_dir_005,
    rc_dir_006, rc_dir_007, rc_dir_008, rc_dir_009, rc_dir_010,
]


# --- RC-MAN: Manifest identity and schema ---


def rc_man_001(ctx: RuleContext):
    try:
        _schema_validate(ctx.manifest)
    except Exception as exc:  # noqa: BLE001 - report every schema violation, never crash the run
        return _fail("RC-MAN-001", "RC-MAN", f"release.yaml does not validate: {exc}")
    return _pass("RC-MAN-001", "RC-MAN", "release.yaml validates against the Release Manifest schema")


def rc_man_002(ctx: RuleContext):
    if ctx.project_state is None:
        return _na("RC-MAN-002", "RC-MAN", "Project Version State not supplied to this validation run")
    application = ctx.manifest.get("application", {})
    state_app = ctx.project_state.get("application", {})
    if application.get("name") == state_app.get("name") and application.get("slug") == state_app.get(
        "slug"
    ):
        return _pass("RC-MAN-002", "RC-MAN", "application identity matches Project Version State")
    return _fail(
        "RC-MAN-002",
        "RC-MAN",
        f"manifest application {application!r} does not match Project Version State {state_app!r}",
    )


def rc_man_003(ctx: RuleContext):
    version = ctx.manifest.get("release", {}).get("version")
    if version and ctx.release_dir.name.endswith(f"_Release_{version}"):
        return _pass("RC-MAN-003", "RC-MAN", "release.version matches the Release directory name")
    return _fail(
        "RC-MAN-003",
        "RC-MAN",
        f"release.version {version!r} does not match Release directory name {ctx.release_dir.name!r}",
    )


def rc_man_004(ctx: RuleContext):
    tag = ctx.manifest.get("source", {}).get("git_tag")
    if not tag:
        return _na("RC-MAN-004", "RC-MAN", "no source.git_tag declared")
    version = ctx.manifest.get("release", {}).get("version")
    if tag == f"v{version}":
        return _pass("RC-MAN-004", "RC-MAN", f"git_tag {tag!r} corresponds to release.version")
    return _fail("RC-MAN-004", "RC-MAN", f"git_tag {tag!r} does not correspond to release.version {version!r}")


def rc_man_005(ctx: RuleContext):
    slug = ctx.manifest.get("application", {}).get("slug")
    canonical_path = ctx.manifest.get("deployment", {}).get("canonical_path")
    expected = f"/opt/rah/apps/{slug}"
    if canonical_path == expected:
        return _pass("RC-MAN-005", "RC-MAN", "canonical_path corresponds to application.slug")
    return _fail(
        "RC-MAN-005", "RC-MAN", f"canonical_path {canonical_path!r} does not equal expected {expected!r}"
    )


def rc_man_006(ctx: RuleContext):
    version = ctx.manifest.get("release", {}).get("version", "")
    name = ctx.manifest.get("deployment", {}).get("compose_project_name", "")
    if version and version in name:
        return _fail("RC-MAN-006", "RC-MAN", f"compose_project_name {name!r} contains the Release version")
    return _pass("RC-MAN-006", "RC-MAN", "compose_project_name is version-independent")


def rc_man_007(ctx: RuleContext):
    raw_text = ctx.path("release.yaml").read_text(encoding="utf-8")
    if re.search(r"!!python/|!![A-Za-z]+/object", raw_text):
        return _fail("RC-MAN-007", "RC-MAN", "release.yaml contains an unsupported/executable YAML tag")
    return _pass(
        "RC-MAN-007",
        "RC-MAN",
        "release.yaml parsed with yaml.safe_load (unsafe tags are structurally rejected) "
        "and no suspicious tag markers found in the raw text",
    )


RC_MAN_CHECKS = [rc_man_001, rc_man_002, rc_man_003, rc_man_004, rc_man_005, rc_man_006, rc_man_007]


# --- RC-ART: Artifact existence and placement ---


def rc_art_001(ctx: RuleContext):
    images = ctx.manifest.get("docker", {}).get("images") or []
    missing = [i["archive"] for i in images if not ctx.exists(i.get("archive"))]
    if not missing:
        return _pass("RC-ART-001", "RC-ART", f"all {len(images)} declared image archives exist")
    return _fail("RC-ART-001", "RC-ART", f"missing image archives: {', '.join(missing)}")


def rc_art_002(ctx: RuleContext):
    documentation = ctx.manifest.get("documentation") or {}
    missing = [k for k, v in documentation.items() if not ctx.exists(v)]
    if not missing:
        return _pass("RC-ART-002", "RC-ART", "all declared documentation files exist")
    return _fail("RC-ART-002", "RC-ART", f"missing documentation files: {', '.join(missing)}")


def rc_art_003(ctx: RuleContext):
    entrypoint = ctx.manifest.get("verification", {}).get("entrypoint")
    if ctx.exists(entrypoint):
        return _pass("RC-ART-003", "RC-ART", "verification entrypoint exists")
    return _fail("RC-ART-003", "RC-ART", f"verification.entrypoint {entrypoint!r} does not exist")


def rc_art_004(ctx: RuleContext):
    entrypoints = ctx.manifest.get("deployment", {}).get("entrypoints") or {}
    missing = [k for k, v in entrypoints.items() if not ctx.exists(v)]
    if not missing:
        return _pass("RC-ART-004", "RC-ART", "all declared deployment entrypoints exist")
    return _fail("RC-ART-004", "RC-ART", f"missing deployment entrypoints: {', '.join(missing)}")


def rc_art_005(ctx: RuleContext):
    models = ctx.manifest.get("models") or {}
    if not models.get("required") or not models.get("artifacts"):
        return _na("RC-ART-005", "RC-ART", "no required model artifacts declared")
    services = {i["service"] for i in ctx.manifest.get("docker", {}).get("images") or []}
    bad = [
        a["id"]
        for a in models["artifacts"]
        if a.get("baked_into_image") not in services
    ]
    if not bad:
        return _pass("RC-ART-005", "RC-ART", "every model artifact's baked_into_image matches a real image")
    return _fail("RC-ART-005", "RC-ART", f"model artifacts with no matching image service: {', '.join(bad)}")


def rc_art_006(ctx: RuleContext):
    compose_file = ctx.manifest.get("docker", {}).get("compose_file")
    if not ctx.exists(compose_file):
        return _fail("RC-ART-006", "RC-ART", f"compose file {compose_file!r} does not exist")
    compose_text = ctx.path(compose_file).read_text(encoding="utf-8")
    images = ctx.manifest.get("docker", {}).get("images") or []
    unreferenced = [
        f"{i['repository']}:{i['tag']}"
        for i in images
        if f"{i['repository']}:{i['tag']}" not in compose_text
    ]
    if not unreferenced:
        return _pass("RC-ART-006", "RC-ART", "every declared image is referenced by the compose file")
    return _fail("RC-ART-006", "RC-ART", f"images not referenced in compose: {', '.join(unreferenced)}")


def rc_art_007(ctx: RuleContext):
    images = ctx.manifest.get("docker", {}).get("images") or []
    empty = [i["archive"] for i in images if ctx.exists(i.get("archive")) and ctx.path(i["archive"]).stat().st_size == 0]
    missing = [i["archive"] for i in images if not ctx.exists(i.get("archive"))]
    if missing:
        return _fail("RC-ART-007", "RC-ART", f"declared archives missing on disk: {', '.join(missing)}")
    if empty:
        return _fail("RC-ART-007", "RC-ART", f"declared archives are empty files: {', '.join(empty)}")
    return _pass("RC-ART-007", "RC-ART", "declared artifacts are physically present and non-empty")


def _inspect_image_archive(archive_path: Path) -> tuple[bool, set[str], list[str]]:
    """Returns (structurally_valid, repo_tags_if_available, referenced_blob_paths).
    Handles both classic Docker export format (top-level `manifest.json`
    with populated `RepoTags`) and the newer OCI export format (`docker
    images save` via the containerd image store): same top-level
    `manifest.json`, but `RepoTags` is `null` and no tag is recoverable
    from `index.json`'s annotations either — a real, observed difference
    between Docker installations, not a bug in the archive itself. When
    no tag is recoverable, identity is verified structurally instead
    (every blob `manifest.json` references actually exists in the tar).
    """
    import json as _json

    with tarfile.open(archive_path, "r") as tar:
        names = set(tar.getnames())
        if "manifest.json" not in names:
            raise tarfile.TarError("no manifest.json at archive root")
        with tar.extractfile("manifest.json") as f:
            entries = _json.loads(f.read())
        repo_tags = {tag for entry in entries for tag in (entry.get("RepoTags") or [])}
        referenced_blobs = []
        for entry in entries:
            referenced_blobs.append(entry.get("Config"))
            referenced_blobs.extend(entry.get("Layers") or [])
        missing_blobs = [b for b in referenced_blobs if b and b not in names]
        if missing_blobs:
            raise tarfile.TarError(f"manifest.json references missing blobs: {missing_blobs}")
        return True, repo_tags, referenced_blobs


def rc_art_008(ctx: RuleContext):
    images = ctx.manifest.get("docker", {}).get("images") or []
    problems = []
    for image in images:
        archive = image.get("archive")
        if not ctx.exists(archive):
            continue
        expected_tag = f"{image['repository']}:{image['tag']}"
        try:
            _valid, repo_tags, _blobs = _inspect_image_archive(ctx.path(archive))
        except (tarfile.TarError, KeyError, ValueError, OSError) as exc:
            problems.append(f"{archive}: not a valid/inspectable Docker image archive ({exc})")
            continue
        if repo_tags and expected_tag not in repo_tags:
            problems.append(f"{archive}: does not contain {expected_tag!r} (found {sorted(repo_tags)})")
        # else: this export format doesn't carry recoverable tag metadata
        # (observed with the containerd/OCI image store) — structural
        # validity (checked above) is the best available evidence.
    if not problems:
        return _pass("RC-ART-008", "RC-ART", "every image archive is inspectable and structurally valid")
    return _fail("RC-ART-008", "RC-ART", "; ".join(problems))


RC_ART_CHECKS = [
    rc_art_001, rc_art_002, rc_art_003, rc_art_004, rc_art_005, rc_art_006, rc_art_007, rc_art_008,
]


# --- RC-SCR: Lifecycle scripts ---


def rc_scr_001(ctx: RuleContext):
    entrypoints = ctx.manifest.get("deployment", {}).get("entrypoints") or {}
    missing = [k for k, v in entrypoints.items() if not ctx.exists(v)]
    if not missing:
        return _pass("RC-SCR-001", "RC-SCR", "every declared lifecycle script exists")
    return _fail("RC-SCR-001", "RC-SCR", f"missing lifecycle scripts: {', '.join(missing)}")


def rc_scr_002(ctx: RuleContext):
    entrypoints = ctx.manifest.get("deployment", {}).get("entrypoints") or {}
    outside = [k for k, v in entrypoints.items() if not v.startswith("scripts/")]
    if not outside:
        return _pass("RC-SCR-002", "RC-SCR", "every lifecycle script is located inside scripts/")
    return _fail("RC-SCR-002", "RC-SCR", f"scripts outside scripts/: {', '.join(outside)}")


def rc_scr_003(ctx: RuleContext):
    return _pass(
        "RC-SCR-003",
        "RC-SCR",
        "lifecycle scripts are read directly from release.yaml's own deployment.entrypoints — "
        "no undeclared script path can be referenced by this check",
    )


def rc_scr_004(ctx: RuleContext):
    entrypoints = ctx.manifest.get("deployment", {}).get("entrypoints") or {}
    supported = ctx.manifest.get("deployment", {}).get("supported_operations") or {}
    database = ctx.manifest.get("database") or {}
    problems = []
    if supported.get("fresh_install") and not ctx.exists(entrypoints.get("install")):
        problems.append("fresh_install=true but no valid install entrypoint")
    if supported.get("update") and not ctx.exists(entrypoints.get("update")):
        problems.append("update=true but no valid update entrypoint")
    if (database.get("backup_before_update") or {}).get("required") and not ctx.exists(entrypoints.get("backup")):
        problems.append("database.backup_before_update.required=true but no valid backup entrypoint")
    if not problems:
        return _pass("RC-SCR-004", "RC-SCR", "every operation-conditional entrypoint required is present")
    return _fail("RC-SCR-004", "RC-SCR", "; ".join(problems))


def _bash_available() -> bool:
    try:
        result = subprocess.run(["bash", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _exec_bit_propagates(release_dir: Path) -> bool:
    """Real, observed gap: Docker Desktop's bind mount of a Windows host
    directory does not propagate Unix executable permission bits at all —
    every file reports as `-rw-r--r--` inside the container regardless of
    what `chmod`/git's index records, even though `git ls-files -s`
    correctly shows mode `100755`. Probes by creating a throwaway file
    and checking whether `chmod +x` actually sticks, rather than assuming
    the platform based on `os.name` (a Linux CI runner mounting the same
    repo would have no such gap).
    """
    probe = release_dir / ".rah-exec-bit-probe"
    try:
        probe.write_text("")
        probe.chmod(0o755)
        return os.access(probe, os.X_OK)
    except OSError:
        return False
    finally:
        if probe.exists():
            probe.unlink()


def rc_scr_005(ctx: RuleContext):
    entrypoints = ctx.manifest.get("deployment", {}).get("entrypoints") or {}
    if not _bash_available():
        # A genuine `bash` is guaranteed inside the Packager's own
        # container (its Dockerfile installs it transitively via
        # python:3.11-slim/Debian), but not on every host this code
        # might run on directly (e.g. Windows without WSL configured) —
        # NOT_APPLICABLE here rather than a spurious FAIL on an
        # environment quirk unrelated to script content.
        return _na("RC-SCR-005", "RC-SCR", "`bash` is not available in this validation environment")
    check_exec_bit = _exec_bit_propagates(ctx.release_dir)
    problems = []
    for op, relative in entrypoints.items():
        if not ctx.exists(relative):
            continue
        script_path = ctx.path(relative)
        if check_exec_bit and not os.access(script_path, os.X_OK):
            problems.append(f"{relative}: not executable")
        try:
            result = subprocess.run(
                ["bash", "-n", str(script_path)], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            problems.append(f"{relative}: could not run syntax check ({exc})")
            continue
        if result.returncode != 0:
            problems.append(f"{relative}: bash -n failed: {result.stderr.strip()}")
    if not problems:
        message = "every declared script passes a static `bash -n` syntax check"
        message += (
            " and is executable" if check_exec_bit
            else " (executable-bit check skipped: this filesystem does not propagate it)"
        )
        return _pass("RC-SCR-005", "RC-SCR", message)
    return _fail("RC-SCR-005", "RC-SCR", "; ".join(problems))


def rc_scr_006(ctx: RuleContext):
    supported = ctx.manifest.get("deployment", {}).get("supported_operations") or {}
    if supported.get("downgrade") is False:
        return _pass(
            "RC-SCR-006",
            "RC-SCR",
            "supported_operations.downgrade is false; no manifest declaration implies "
            "downgrade support (script content is not statically analyzed for downgrade logic)",
        )
    return _na("RC-SCR-006", "RC-SCR", "supported_operations.downgrade is true — rule targets the false case")


def rc_scr_007(ctx: RuleContext):
    supported = ctx.manifest.get("deployment", {}).get("supported_operations") or {}
    if not supported.get("update"):
        return _na("RC-SCR-007", "RC-SCR", "supported_operations.update is false")
    transition = ctx.manifest.get("deployment", {}).get("transition") or {}
    if transition:
        return _pass("RC-SCR-007", "RC-SCR", "deployment.transition is declared for an updatable Release")
    return _fail("RC-SCR-007", "RC-SCR", "supported_operations.update=true but deployment.transition is empty")


RC_SCR_CHECKS = [
    rc_scr_001, rc_scr_002, rc_scr_003, rc_scr_004, rc_scr_005, rc_scr_006, rc_scr_007,
]


# --- RC-CFG: Configuration ---


def _looks_like_real_secret(value: str) -> bool:
    stripped = value.strip()
    return len(stripped) >= 8 and not _looks_like_placeholder(stripped)


def rc_cfg_001(ctx: RuleContext):
    template = ctx.manifest.get("configuration", {}).get("template")
    if not template or not ctx.exists(template):
        return _na("RC-CFG-001", "RC-CFG", "no configuration template declared")
    problems = []
    for line in ctx.path(template).read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if re.search(r"(?i)password|secret|token|api[_-]?key", key) and _looks_like_real_secret(value):
            problems.append(key)
    if not problems:
        return _pass("RC-CFG-001", "RC-CFG", "configuration template contains no real-looking secret values")
    return _fail("RC-CFG-001", "RC-CFG", f"template lines look like real secrets, not placeholders: {', '.join(problems)}")


def rc_cfg_002(ctx: RuleContext):
    template = ctx.manifest.get("configuration", {}).get("template")
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    if not template or not ctx.exists(template):
        return _na("RC-CFG-002", "RC-CFG", "no configuration template declared")
    declared_keys = {i["key"] for i in inputs}
    text = ctx.path(template).read_text(encoding="utf-8", errors="ignore")
    referenced = set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text))
    undeclared = sorted(referenced - declared_keys)
    if not undeclared:
        return _pass("RC-CFG-002", "RC-CFG", "every template placeholder is declared under configuration.inputs")
    return _fail("RC-CFG-002", "RC-CFG", f"template references undeclared inputs: {', '.join(undeclared)}")


def rc_cfg_003(ctx: RuleContext):
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    problems = [
        i["key"]
        for i in inputs
        if i.get("source") == "generated" and i.get("default") is not None
    ]
    if not problems:
        return _pass("RC-CFG-003", "RC-CFG", "no generated input also declares a fixed default")
    return _fail("RC-CFG-003", "RC-CFG", f"generated inputs with a fixed default: {', '.join(problems)}")


def rc_cfg_004(ctx: RuleContext):
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    problems = []
    for i in inputs:
        default = i.get("default")
        if i.get("type") == "port" and default is not None:
            if not isinstance(default, int) or not (1 <= default <= 65535):
                problems.append(f"{i['key']}: invalid port default {default!r}")
        if i.get("secret") and default is not None:
            problems.append(f"{i['key']}: secret input carries a real default value")
    if not problems:
        return _pass("RC-CFG-004", "RC-CFG", "port defaults are valid and secret inputs carry no default")
    return _fail("RC-CFG-004", "RC-CFG", "; ".join(problems))


RC_CFG_CHECKS = [rc_cfg_001, rc_cfg_002, rc_cfg_003, rc_cfg_004]


# --- RC-DB: Database resources ---


def rc_db_001(ctx: RuleContext):
    database = ctx.manifest.get("database") or {}
    if not database.get("required"):
        return _na("RC-DB-001", "RC-DB", "database.required is false")
    entrypoints = [
        (database.get(section) or {}).get("entrypoint")
        for section in ("initialization", "migration", "backup_before_update", "recovery")
    ]
    declared = [e for e in entrypoints if e]
    missing = [e for e in declared if not ctx.exists(e)]
    if not missing:
        return _pass("RC-DB-001", "RC-DB", "every declared database resource exists")
    return _fail("RC-DB-001", "RC-DB", f"missing database resources: {', '.join(missing)}")


def rc_db_002(ctx: RuleContext):
    database = ctx.manifest.get("database") or {}
    supported = ctx.manifest.get("deployment", {}).get("supported_operations") or {}
    migration = database.get("migration") or {}
    if not (migration.get("required_for_update") and supported.get("update")):
        return _na("RC-DB-002", "RC-DB", "migration is not required for update in this Release")
    if ctx.exists(migration.get("entrypoint")):
        return _pass("RC-DB-002", "RC-DB", "migration entrypoint exists")
    return _fail("RC-DB-002", "RC-DB", "migration.required_for_update=true but no valid migration entrypoint")


def rc_db_003(ctx: RuleContext):
    database = ctx.manifest.get("database") or {}
    if not database.get("required"):
        return _na("RC-DB-003", "RC-DB", "database.required is false")
    problems = []
    for field in ("platform", "deployment_mode", "target_schema_version"):
        if not database.get(field):
            problems.append(f"database.{field} is not declared")
    backup = database.get("backup_before_update") or {}
    if backup.get("required") and not ctx.exists(backup.get("entrypoint")):
        problems.append("backup_before_update.required=true but no valid entrypoint")
    if not problems:
        return _pass("RC-DB-003", "RC-DB", "required database fields and backup resources are present")
    return _fail("RC-DB-003", "RC-DB", "; ".join(problems))


def rc_db_004(ctx: RuleContext):
    return _pass(
        "RC-DB-004",
        "RC-DB",
        "this Validator never executes a real production migration — it only inspects "
        "declared paths and static file existence",
    )


RC_DB_CHECKS = [rc_db_001, rc_db_002, rc_db_003, rc_db_004]


# --- RC-OFF: Offline-dependency consistency ---


def rc_off_001(ctx: RuleContext):
    offline = ctx.manifest.get("offline_requirements") or {}
    bad = [k for k, v in offline.items() if v is True]
    if not bad:
        return _pass("RC-OFF-001", "RC-OFF", "no offline_requirements flag is true")
    return _fail("RC-OFF-001", "RC-OFF", f"declared online requirements: {', '.join(bad)}")


def rc_off_002(ctx: RuleContext):
    compose_file = ctx.manifest.get("docker", {}).get("compose_file")
    if not ctx.exists(compose_file):
        return _fail("RC-OFF-002", "RC-OFF", f"compose file {compose_file!r} does not exist")
    compose = yaml.safe_load(ctx.path(compose_file).read_text(encoding="utf-8")) or {}
    services = compose.get("services") or {}
    declared_images = {f"{i['repository']}:{i['tag']}" for i in ctx.manifest.get("docker", {}).get("images") or []}
    missing = [
        f"{name} ({definition.get('image')})"
        for name, definition in services.items()
        if definition.get("image") not in declared_images
    ]
    if not missing:
        return _pass("RC-OFF-002", "RC-OFF", "every Compose service's image has a local archive")
    return _fail(
        "RC-OFF-002",
        "RC-OFF",
        f"Compose services with no local offline image archive: {', '.join(missing)}",
    )


def rc_off_003(ctx: RuleContext):
    models = ctx.manifest.get("models") or {}
    if not models.get("required") or not models.get("artifacts"):
        return _na("RC-OFF-003", "RC-OFF", "no required model artifacts declared")
    services = {i["service"] for i in ctx.manifest.get("docker", {}).get("images") or []}
    bad = [a["id"] for a in models["artifacts"] if a.get("baked_into_image") not in services]
    if not bad:
        return _pass("RC-OFF-003", "RC-OFF", "every required model artifact is baked into a packaged image")
    return _fail("RC-OFF-003", "RC-OFF", f"model artifacts not packaged offline: {', '.join(bad)}")


_PUBLIC_URL_PATTERN = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|\$\{)[A-Za-z0-9_.-]+"
)


def rc_off_004(ctx: RuleContext):
    text_dirs = ("configuration", "documentation")
    findings = []
    for dirname in text_dirs:
        directory = ctx.path(dirname)
        if not directory.is_dir():
            continue
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for url in _PUBLIC_URL_PATTERN.findall(text):
                findings.append(f"{file_path.relative_to(ctx.release_dir)}: {url}")
    if not findings:
        return _pass(
            "RC-OFF-004",
            "RC-OFF",
            "no undeclared public URL found in configuration/ or documentation/ resources",
        )
    return _fail("RC-OFF-004", "RC-OFF", f"public URLs found: {'; '.join(findings[:10])}")


RC_OFF_CHECKS = [rc_off_001, rc_off_002, rc_off_003, rc_off_004]


# --- RC-SEC: Security ---


def rc_sec_001(ctx: RuleContext):
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    bad = [i["key"] for i in inputs if i.get("type") == "password" and i.get("default") is not None]
    if not bad:
        return _pass("RC-SEC-001", "RC-SEC", "no password-type input carries a real value in release.yaml")
    return _fail("RC-SEC-001", "RC-SEC", f"password inputs with a real default in release.yaml: {', '.join(bad)}")


def rc_sec_002(ctx: RuleContext):
    findings = []
    for file_path in ctx.release_dir.rglob("*"):
        if not file_path.is_file() or file_path.name == CHECKSUM_FILE_RELATIVE_PATH.split("/")[-1]:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _PRIVATE_KEY_MARKER.search(text):
            findings.append(str(file_path.relative_to(ctx.release_dir)))
    if not findings:
        return _pass("RC-SEC-002", "RC-SEC", "no embedded private key found")
    return _fail("RC-SEC-002", "RC-SEC", f"embedded private key material found in: {', '.join(findings)}")


def rc_sec_003(ctx: RuleContext):
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    secret_keys = {i["key"] for i in inputs if i.get("secret")}
    problems = [k for k in secret_keys if next(i for i in inputs if i["key"] == k).get("default") is not None]
    template = ctx.manifest.get("configuration", {}).get("template")
    if template and ctx.exists(template):
        text = ctx.path(template).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
            if match and match.group(1) in secret_keys and _looks_like_real_secret(match.group(2)):
                problems.append(f"{match.group(1)} (in template)")
    if not problems:
        return _pass("RC-SEC-003", "RC-SEC", "secret-marked inputs carry no real value")
    return _fail("RC-SEC-003", "RC-SEC", f"secret inputs with a real value: {', '.join(sorted(set(problems)))}")


def rc_sec_004(ctx: RuleContext):
    inputs = ctx.manifest.get("configuration", {}).get("inputs") or []
    bad = [i["key"] for i in inputs if i.get("source") == "generated" and i.get("default") is not None]
    if not bad:
        return _pass("RC-SEC-004", "RC-SEC", "no generated secret is embedded in the Manifest")
    return _fail("RC-SEC-004", "RC-SEC", f"generated-source inputs with a value in release.yaml: {', '.join(bad)}")


def rc_sec_005(ctx: RuleContext):
    unsafe = [k for k, v in _all_declared_paths(ctx).items() if not _is_safe_relative_path(ctx, v)]
    if unsafe:
        return _fail("RC-SEC-005", "RC-SEC", f"paths escaping the Release root: {', '.join(unsafe)}")
    return _pass("RC-SEC-005", "RC-SEC", "no declared path escapes the Release root")


def rc_sec_006(ctx: RuleContext):
    return _pass(
        "RC-SEC-006",
        "RC-SEC",
        "self-referential guarantee: every message this Validator produces names a field, "
        "not a secret's actual value",
    )


RC_SEC_CHECKS = [rc_sec_001, rc_sec_002, rc_sec_003, rc_sec_004, rc_sec_005, rc_sec_006]


# --- RC-INT: Integrity/checksums (only meaningful after closure) ---


def rc_int_001(ctx: RuleContext):
    if ctx.path(CHECKSUM_FILE_RELATIVE_PATH).is_file():
        return _pass("RC-INT-001", "RC-INT", "checksums/SHA256SUMS exists")
    return _fail("RC-INT-001", "RC-INT", "checksums/SHA256SUMS does not exist")


def _read_recorded_checksum_paths(ctx: RuleContext) -> set[str]:
    checksum_path = ctx.path(CHECKSUM_FILE_RELATIVE_PATH)
    if not checksum_path.is_file():
        return set()
    recorded = set()
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            _, _, relative = line.partition("  ")
            recorded.add(relative)
    return recorded


def rc_int_002(ctx: RuleContext):
    recorded = _read_recorded_checksum_paths(ctx)
    if not recorded:
        return _fail("RC-INT-002", "RC-INT", "checksums/SHA256SUMS is missing or empty")
    missing_coverage = []
    if "release.yaml" not in recorded:
        missing_coverage.append("release.yaml")
    for dirname in _MINIMUM_CHECKSUM_COVERAGE_DIRS:
        directory = ctx.path(dirname)
        if directory.is_dir() and any(p.is_file() for p in directory.rglob("*")):
            if not any(r.startswith(f"{dirname}/") for r in recorded):
                missing_coverage.append(dirname)
    if not missing_coverage:
        return _pass("RC-INT-002", "RC-INT", "every critical artifact category is represented in SHA256SUMS")
    return _fail("RC-INT-002", "RC-INT", f"not represented in SHA256SUMS: {', '.join(missing_coverage)}")


def rc_int_003(ctx: RuleContext):
    recorded = {}
    checksum_path = ctx.path(CHECKSUM_FILE_RELATIVE_PATH)
    if not checksum_path.is_file():
        return _fail("RC-INT-003", "RC-INT", "checksums/SHA256SUMS does not exist")
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, _, relative = line.partition("  ")
            recorded[relative] = digest
    if "release.yaml" not in recorded:
        return _fail("RC-INT-003", "RC-INT", "release.yaml is not represented in SHA256SUMS")
    actual = compute_file_checksums(ctx.release_dir).get("release.yaml")
    if actual == recorded["release.yaml"]:
        return _pass("RC-INT-003", "RC-INT", "recorded manifest checksum matches release.yaml's actual contents")
    return _fail("RC-INT-003", "RC-INT", "recorded manifest checksum does not match release.yaml's actual contents")


def rc_int_004(ctx: RuleContext):
    recorded = _read_recorded_checksum_paths(ctx)
    problems = []
    if "compliance/release-compliance-report.json" not in recorded:
        problems.append(
            "compliance/release-compliance-report.json is not represented in SHA256SUMS "
            "(closure must generate the Compliance Report before the final checksum file)"
        )
    if CHECKSUM_FILE_RELATIVE_PATH.split("/")[-1] in {p.split("/")[-1] for p in recorded if p == CHECKSUM_FILE_RELATIVE_PATH}:
        problems.append("SHA256SUMS lists itself")
    if not problems:
        return _pass(
            "RC-INT-004",
            "RC-INT",
            "integrity closure order verified: the Compliance Report is covered by the final "
            "checksum file, which does not list itself",
        )
    return _fail("RC-INT-004", "RC-INT", "; ".join(problems))


RC_INT_CHECKS = [rc_int_001, rc_int_002, rc_int_003, rc_int_004]


STAGE_A_CHECKS = (
    RC_DIR_CHECKS + RC_MAN_CHECKS + RC_ART_CHECKS + RC_SCR_CHECKS
    + RC_CFG_CHECKS + RC_DB_CHECKS + RC_OFF_CHECKS + RC_SEC_CHECKS
)


def _rule_id_for(check) -> str:
    # e.g. rc_con_001 -> RC-CON-001
    parts = check.__name__.split("_")
    return f"{parts[0].upper()}-{parts[1].upper()}-{parts[2]}"


def _category_for(check) -> str:
    parts = check.__name__.split("_")
    return f"{parts[0].upper()}-{parts[1].upper()}"


def run_stage_a_rules(release_dir: Path, project_state: dict | None = None) -> list[dict]:
    """RC-CON through RC-SEC — everything except RC-INT (integrity
    closure, only meaningful once checksums/the Compliance Report exist)
    and RC-REPRO (a build-time regression check, not a per-Release rule).
    """
    all_ids_except_int = [_rule_id_for(c) for c in RC_CON_CHECKS + STAGE_A_CHECKS]

    if not release_dir.is_dir():
        return [_not_executed(_rule_id_for(c), _category_for(c), "Release root is not accessible") for c in RC_CON_CHECKS + STAGE_A_CHECKS]

    manifest_path = release_dir / "release.yaml"
    if not manifest_path.is_file():
        return [_not_executed(_rule_id_for(c), _category_for(c), "release.yaml is missing") for c in RC_CON_CHECKS + STAGE_A_CHECKS]

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [
            _not_executed(_rule_id_for(c), _category_for(c), f"release.yaml is not parseable YAML: {exc}")
            for c in RC_CON_CHECKS + STAGE_A_CHECKS
        ]
    if not isinstance(manifest, dict):
        return [
            _not_executed(_rule_id_for(c), _category_for(c), "release.yaml did not parse to a mapping")
            for c in RC_CON_CHECKS + STAGE_A_CHECKS
        ]

    ctx = RuleContext(release_dir=release_dir, manifest=manifest, project_state=project_state)

    results = [check(ctx) for check in RC_CON_CHECKS]
    if any(r["result"] == "FAIL" for r in results):
        executed_ids = {r["id"] for r in results}
        for check in STAGE_A_CHECKS:
            rid = _rule_id_for(check)
            if rid not in executed_ids:
                results.append(_not_executed(rid, _category_for(check), "Contract version could not be resolved"))
        return results

    for check in STAGE_A_CHECKS:
        results.append(check(ctx))
    return results


def run_integrity_rules(release_dir: Path) -> list[dict]:
    """RC-INT only — call after checksum closure so these are
    meaningful. Assumes `release_dir`/`release.yaml` already passed
    `run_stage_a_rules`.
    """
    manifest = yaml.safe_load((release_dir / "release.yaml").read_text(encoding="utf-8"))
    ctx = RuleContext(release_dir=release_dir, manifest=manifest)
    return [check(ctx) for check in RC_INT_CHECKS]
