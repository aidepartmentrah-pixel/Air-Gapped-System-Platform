"""Common result envelope every `rah` CLI command returns as JSON.

P0 completion gate requires: "CLI returns a valid JSON result object."
Every command's stdout is exactly one JSON object shaped like this —
never partial output, never a bare traceback.
"""

from __future__ import annotations

import json
from typing import Any

from rah_packager.errors import PackagerError


def ok(command: str, result: dict[str, Any]) -> dict:
    return {"ok": True, "command": command, "result": result, "error": None}


def failure(command: str, error: PackagerError) -> dict:
    return {"ok": False, "command": command, "result": None, "error": error.to_dict()}


def render(envelope: dict) -> str:
    return json.dumps(envelope, indent=2, sort_keys=True)
