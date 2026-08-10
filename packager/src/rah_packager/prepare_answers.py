"""`rah prepare-answers` — P3 subtask 2, the actual Claude API call.

Three-tier question design (see docs/decisions/engineering-answers-and-staleness.md):
1. Fields P2 already discovered facts for get a pre-filled suggestion here
   (`build_suggestions`) that Claude is asked to confirm or override.
2. Contract-default fields (mostly `false`) get their default as a
   suggestion too.
3. Everything else is a genuinely open question — no suggestion is given,
   Claude answers from the bundled file contents alone.

Re-run behavior (user-confirmed): unconditional overwrite. Unlike `rah
init`, there is no "already initialized" refusal — every run replaces
`.rah/engineering-answers.json` with a fresh answer, always re-derived
from the current repository state.

`based_on` is never asked of Claude — the Packager computes it
deterministically from the same `ProjectInspectionResult` it sends,
exactly like `validate_answers.py` recomputes it for comparison.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import anthropic

from rah_packager.engineering_answers import (
    ENGINEERING_ANSWERS_SCHEMA,
    SCHEMA_VERSION,
    compute_inspection_fingerprint,
    validate_engineering_answers_schema,
)
from rah_packager.errors import (
    ClaudeAPIError,
    ClaudeAPIKeyMissingError,
    ClaudeAuthenticationError,
    ClaudeConnectionError,
    ClaudeRateLimitedError,
    ClaudeRefusalError,
    EngineeringAnswersWriteError,
)
from rah_packager.inspection import inspect_project
from rah_packager.repository import require_git_repository, validate_project_path
from rah_packager.validate_answers import default_answers_path

_MODEL = "claude-opus-5"
_MAX_TOKENS = 8000
_MAX_FILE_BYTES = 20_000

_ENTRYPOINT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "install": ("install",),
    "update": ("update",),
    "verify": ("verify", "valid"),
    "backup": ("backup",),
    "restore": ("restore",),
}

_DOCUMENTATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "release_notes": ("release_notes", "release-notes"),
    "installation": ("install",),
    "update": ("update",),
    "recovery": ("backup_restore", "backup-restore", "recovery", "restore"),
    "known_issues": ("troubleshoot", "known_issue", "issue"),
}

_DATABASE_IMAGE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sqlserver": ("mssql", "sqlserver", "sql-server"),
    "postgresql": ("postgres",),
    "mysql": ("mysql", "mariadb"),
    "sqlite": ("sqlite",),
}


def _guess_by_keyword(
    candidates: list[str], keyword_map: dict[str, tuple[str, ...]]
) -> dict[str, str]:
    guesses: dict[str, str] = {}
    for slot, keywords in keyword_map.items():
        for candidate in candidates:
            name = candidate.rsplit("/", 1)[-1].lower()
            if any(keyword in name for keyword in keywords):
                guesses[slot] = candidate
                break
    return guesses


def _guess_database_platform(services: list[dict]) -> str | None:
    for service in services:
        image = (service.get("image") or "").lower()
        for platform, keywords in _DATABASE_IMAGE_KEYWORDS.items():
            if any(keyword in image for keyword in keywords):
                return platform
    return None


def build_suggestions(inspection_result: dict) -> dict:
    """A partial engineering-answers-shaped dict: only the fields we have a
    suggestion for are present. Tier 1 (discovered-fact guesses) and tier 2
    (Contract defaults) both live here — tier 3 (genuinely open questions)
    is simply everything the returned dict doesn't mention.
    """
    resources = inspection_result.get("application_resources") or {}
    docker = inspection_result.get("docker") or {}

    entrypoints = _guess_by_keyword(resources.get("scripts") or [], _ENTRYPOINT_KEYWORDS)
    documentation = _guess_by_keyword(
        resources.get("documentation") or [], _DOCUMENTATION_KEYWORDS
    )
    database_platform = _guess_database_platform(docker.get("services") or [])

    suggestions: dict = {
        "offline_requirements": {
            "public_internet_required": False,
            "public_registry_required": False,
            "public_cdn_required": False,
            "online_model_registry_required": False,
        },
        "models": {"required": False},
        "client": {"preparation_required": False, "https_required": False},
    }
    if entrypoints:
        suggestions["deployment"] = {"entrypoints": entrypoints}
        if "verify" in entrypoints:
            suggestions["verification"] = {"entrypoint": entrypoints["verify"]}
    if documentation:
        suggestions["documentation"] = documentation
    if database_platform:
        suggestions["database"] = {"platform": database_platform}

    return suggestions


def _read_file_snippet(project_path: Path, relative_path: str) -> str:
    try:
        data = (project_path / relative_path).read_bytes()
    except OSError as exc:
        return f"[could not read {relative_path}: {exc}]"

    truncated = len(data) > _MAX_FILE_BYTES
    if truncated:
        data = data[:_MAX_FILE_BYTES]
    text = data.decode("utf-8", errors="replace")
    return text + "\n... [truncated]" if truncated else text


def build_context_bundle(project_path: Path, inspection_result: dict, suggestions: dict) -> str:
    """The full user-turn text sent to Claude: discovered facts, suggested
    pre-fills, and the actual contents of the files P2 flagged as
    relevant — bounded to what P2 already discovered, not an arbitrary
    repo-wide dump.
    """
    resources = inspection_result.get("application_resources") or {}
    relevant_paths = list(resources.get("scripts") or [])
    relevant_paths += resources.get("documentation") or []
    relevant_paths += resources.get("configuration_templates") or []
    compose_file = (inspection_result.get("docker") or {}).get("compose_file")
    if compose_file:
        relevant_paths.append(compose_file)

    file_sections = [
        f"--- {rel_path} ---\n{_read_file_snippet(project_path, rel_path)}"
        for rel_path in relevant_paths
    ]

    parts = [
        "You are filling in the engineering-judgment gaps for a RAH Application "
        "Release manifest. You will call the `submit_engineering_answers` tool "
        "exactly once with your complete answer.",
        "",
        "Deterministic facts already discovered from the repository (given, do not "
        "re-derive):",
        json.dumps(inspection_result, indent=2, sort_keys=True),
        "",
        "Suggested pre-filled values for some fields — confirm, correct, or "
        "override each one based on the real file contents below; do not treat "
        "them as certain:",
        json.dumps(suggestions, indent=2, sort_keys=True),
        "",
        "Contents of the discovered files, for context:",
        "\n\n".join(file_sections) if file_sections else "(no relevant files discovered)",
        "",
        "Answer every required field in the schema. For fields with a suggested "
        "value above, confirm it or override it based on the actual file "
        "contents. For fields with no suggestion, answer from your own reading "
        "of the repository facts and file contents above. Omit optional fields "
        "you have no basis to answer rather than guessing.",
    ]
    return "\n".join(parts)


def _claude_tool_schema() -> dict:
    schema = copy.deepcopy(ENGINEERING_ANSWERS_SCHEMA)
    for meta_key in ("$schema", "$id", "title", "description"):
        schema.pop(meta_key, None)
    schema["properties"].pop("based_on", None)
    schema["properties"].pop("schema_version", None)
    schema["required"] = [
        field for field in schema["required"] if field not in ("based_on", "schema_version")
    ]
    return schema


def _call_claude_for_answers(context_text: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    tool = {
        "name": "submit_engineering_answers",
        "description": (
            "Submit the structured engineering answers for this application's "
            "Release Manifest."
        ),
        "input_schema": _claude_tool_schema(),
    }
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            tools=[tool],
            tool_choice={"type": "tool", "name": "submit_engineering_answers"},
            messages=[{"role": "user", "content": context_text}],
        )
    except anthropic.AuthenticationError as exc:
        raise ClaudeAuthenticationError(str(exc)) from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeRateLimitedError(str(exc)) from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeConnectionError(str(exc)) from exc
    except anthropic.APIStatusError as exc:
        raise ClaudeAPIError(str(exc)) from exc

    if response.stop_reason == "refusal":
        raise ClaudeRefusalError()

    for block in response.content:
        if block.type == "tool_use":
            return block.input

    raise ClaudeAPIError(
        "Claude did not return a tool_use block despite a forced tool_choice"
    )


def _write_answers_atomically(answers_path: Path, answers: dict) -> None:
    """Same tmp-write, validate, atomic-replace pattern as
    project_state.py's `_write_state_atomically` — the real file is never
    observed partially written or invalid.
    """
    tmp_path = answers_path.with_name(answers_path.name + ".tmp")
    payload = json.dumps(answers, indent=2, sort_keys=True) + "\n"
    try:
        answers_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(payload, encoding="utf-8")
        validate_engineering_answers_schema(json.loads(tmp_path.read_text(encoding="utf-8")))
        os.replace(tmp_path, answers_path)
    except OSError as exc:
        raise EngineeringAnswersWriteError(str(exc)) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def prepare_answers(
    project_path: str | os.PathLike,
    api_key: str | None,
    answers_path: str | os.PathLike | None = None,
) -> dict:
    """`rah prepare-answers`. Always overwrites `.rah/engineering-answers.json`
    if it already exists — confirmed re-run behavior, no "already
    initialized" refusal like `rah init`.
    """
    if not api_key:
        raise ClaudeAPIKeyMissingError()

    path = validate_project_path(project_path)
    require_git_repository(path)

    inspection_result = inspect_project(path)
    suggestions = build_suggestions(inspection_result)
    context_text = build_context_bundle(path, inspection_result, suggestions)

    claude_answer = _call_claude_for_answers(context_text, api_key)

    based_on = {
        "git_commit": inspection_result["git"]["commit"],
        "inspection_fingerprint": compute_inspection_fingerprint(inspection_result),
    }
    # claude_answer first so the deterministic fields always win, in case
    # Claude's output includes keys it shouldn't (schema_version/based_on
    # were stripped from the tool schema, but nothing guarantees the model
    # honors that without `strict: true`).
    full_answers = {**claude_answer, "schema_version": SCHEMA_VERSION, "based_on": based_on}

    # Defensive: the Packager built the forced-tool schema, so a failure here
    # means a bug in this module, not bad input — matches project_state.py's
    # rationale for validating its own construction before writing.
    validate_engineering_answers_schema(full_answers)

    resolved_answers_path = Path(answers_path) if answers_path else default_answers_path(path)
    _write_answers_atomically(resolved_answers_path, full_answers)

    return {
        "answers_path": str(resolved_answers_path),
        "based_on": based_on,
        "schema_valid": True,
    }
