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
from rah_packager.inspection import inspect_project
from rah_packager.logging_config import configure_logging
from rah_packager.project_state import DEFAULT_INITIAL_VERSION, init_project
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


@main.command()
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository to initialize.",
)
@click.option("--name", "name", required=True, help="Human-readable application name.")
@click.option(
    "--slug",
    "slug",
    required=True,
    help="Stable machine-readable application slug (lowercase, hyphenated).",
)
@click.option(
    "--initial-version",
    "initial_version",
    default=DEFAULT_INITIAL_VERSION,
    show_default=True,
    help="Version proposed for the project's first Application Release.",
)
def init(project_path: str, name: str, slug: str, initial_version: str) -> None:
    """Initialize an ordinary Git repository as a Packager-managed project."""
    try:
        data = init_project(project_path, name, slug, initial_version)
    except PackagerError as exc:
        click.echo(render(failure("init", exc)))
        sys.exit(1)
    click.echo(render(ok("init", data)))


@main.command()
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository to inspect.",
)
def inspect(project_path: str) -> None:
    """Inspect the repository and report deterministic project facts."""
    try:
        data = inspect_project(project_path)
    except PackagerError as exc:
        click.echo(render(failure("inspect", exc)))
        sys.exit(1)
    click.echo(render(ok("inspect", data)))


if __name__ == "__main__":
    main()
