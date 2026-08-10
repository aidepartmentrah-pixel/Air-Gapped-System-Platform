"""Logging setup.

Logs go to stderr, always — stdout is reserved exclusively for the one
JSON result envelope a command emits (see result.py). Mixing the two
would break the "CLI returns a valid JSON result object" completion gate
for any caller parsing stdout.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s rah.%(name)s: %(message)s",
    )
