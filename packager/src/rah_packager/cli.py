"""`rah` CLI entry point.

Every subcommand emits exactly one JSON result envelope on stdout (see
result.py) and exits 0 on success, 1 on a structured PackagerError. Logs
go to stderr only, never stdout — a caller parsing stdout as JSON must
never see anything else mixed in.
"""

from __future__ import annotations

import sys

import click

from rah_packager import __version__
from rah_packager.config import Config
from rah_packager.errors import PackagerError
from rah_packager.health import run_health_check
from rah_packager.logging_config import configure_logging
from rah_packager.result import failure, ok, render


@click.group()
@click.version_option(version=__version__, prog_name="rah")
def main() -> None:
    """RAH Packaging Engine CLI."""
    configure_logging(Config.from_env().log_level)


@main.command()
def version() -> None:
    """Print the Packager's own version as a structured result."""
    click.echo(render(ok("version", {"packager_version": __version__})))


@main.command()
def health() -> None:
    """Prove the Packager runtime actually works: Docker connectivity,
    plus mounted repository/output directory checks when configured.
    """
    config = Config.from_env()
    try:
        report = run_health_check(config)
    except PackagerError as exc:
        click.echo(render(failure("health", exc)))
        sys.exit(1)
    click.echo(render(ok("health", report)))


if __name__ == "__main__":
    main()
