"""Anthropic API credential validation.

Mirrors docker_client.py's pattern: make one real, cheap call and turn
whatever the SDK raises into a deterministic PackagerError — never let a
raw SDK exception escape to the CLI. Uses `count_tokens`, not a real
generation: it's a genuine authenticated API call (a bad key still 401s)
without spending output tokens on a validation check nobody reads.
"""

from __future__ import annotations

import anthropic

from rah_packager.errors import (
    ClaudeAPIError,
    ClaudeAuthenticationError,
    ClaudeConnectionError,
    ClaudeRateLimitedError,
)

_VALIDATION_MODEL = "claude-haiku-4-5"


def validate_api_key(api_key: str) -> None:
    """Raises a PackagerError subclass if the key doesn't work. Returns
    None on success — nothing meaningful to report beyond "it authenticated".
    """
    client = anthropic.Anthropic(api_key=api_key)
    try:
        client.messages.count_tokens(
            model=_VALIDATION_MODEL,
            messages=[{"role": "user", "content": "hi"}],
        )
    except anthropic.AuthenticationError as exc:
        raise ClaudeAuthenticationError(str(exc)) from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeRateLimitedError(str(exc)) from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeConnectionError(str(exc)) from exc
    except anthropic.APIStatusError as exc:
        raise ClaudeAPIError(str(exc)) from exc
