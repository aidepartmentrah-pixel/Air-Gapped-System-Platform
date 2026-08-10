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
from rah_packager.construct_release import construct_release
from rah_packager.docker_build import build_release_images
from rah_packager.errors import PackagerError
from rah_packager.health import run_health_check
from rah_packager.inspection import inspect_project
from rah_packager.logging_config import configure_logging
from rah_packager.prepare_answers import prepare_answers
from rah_packager.project_state import DEFAULT_INITIAL_VERSION, init_project
from rah_packager.release_plan import prepare_plan
from rah_packager.result import failure, ok, render
from rah_packager.validate_answers import validate_answers


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


@main.command(name="validate-answers")
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository whose engineering answers to validate.",
)
@click.option(
    "--answers",
    "answers_path",
    default=None,
    type=click.Path(),
    help="Path to engineering-answers.json (defaults to <project>/.rah/engineering-answers.json).",
)
def validate_answers_command(project_path: str, answers_path: str | None) -> None:
    """Validate engineering answers: schema, consistency with the current
    repository, and staleness — no Claude API call.
    """
    try:
        data = validate_answers(project_path, answers_path)
    except PackagerError as exc:
        click.echo(render(failure("validate-answers", exc)))
        sys.exit(1)
    click.echo(render(ok("validate-answers", data)))


@main.command(name="prepare-answers")
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository to prepare engineering answers for.",
)
@click.option(
    "--answers",
    "answers_path",
    default=None,
    type=click.Path(),
    help="Path to write engineering-answers.json to (defaults to <project>/.rah/engineering-answers.json).",
)
def prepare_answers_command(project_path: str, answers_path: str | None) -> None:
    """Ask Claude to fill the engineering-judgment gaps `rah inspect` can't
    determine on its own, and write `.rah/engineering-answers.json`. Always
    overwrites an existing file.
    """
    config = Config.from_env()
    try:
        data = prepare_answers(project_path, config.anthropic_api_key, answers_path)
    except PackagerError as exc:
        click.echo(render(failure("prepare-answers", exc)))
        sys.exit(1)
    click.echo(render(ok("prepare-answers", data)))


@main.command(name="plan")
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository to plan a Release for.",
)
@click.option(
    "--increment",
    "increment",
    default="patch",
    type=click.Choice(["patch", "minor", "major"]),
    show_default=True,
    help="Version increment to propose (ignored before the first Release).",
)
@click.option(
    "--answers",
    "answers_path",
    default=None,
    type=click.Path(),
    help="Path to engineering-answers.json (defaults to <project>/.rah/engineering-answers.json).",
)
def plan(project_path: str, increment: str, answers_path: str | None) -> None:
    """Preview exactly what Release would be built, without building or
    finalizing anything.
    """
    try:
        data = prepare_plan(project_path, increment, answers_path)
    except PackagerError as exc:
        click.echo(render(failure("plan", exc)))
        sys.exit(1)
    click.echo(render(ok("plan", data)))


@main.command(name="build")
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository whose Compose-declared images to build.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(),
    help="Temporary build workspace to export image archives into.",
)
@click.option("--slug", "application_slug", required=True, help="Application slug for image naming.")
@click.option("--version", "version", required=True, help="Version to tag built images with.")
def build(project_path: str, output_dir: str, application_slug: str, version: str) -> None:
    """Build every Compose-declared service image, tag it, and export it to
    a temporary build workspace. Does not finalize a Release.
    """
    try:
        data = build_release_images(project_path, application_slug, version, output_dir)
    except PackagerError as exc:
        click.echo(render(failure("build", exc)))
        sys.exit(1)
    click.echo(render(ok("build", data)))


@main.command(name="construct")
@click.option(
    "--project",
    "project_path",
    required=True,
    type=click.Path(),
    help="Path to the application repository to construct a candidate Release for.",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(),
    help="Directory the candidate Release directory is created under.",
)
@click.option(
    "--increment",
    "increment",
    default="patch",
    type=click.Choice(["patch", "minor", "major"]),
    show_default=True,
    help="Version increment to propose (ignored before the first Release).",
)
@click.option(
    "--answers",
    "answers_path",
    default=None,
    type=click.Path(),
    help="Path to engineering-answers.json (defaults to <project>/.rah/engineering-answers.json).",
)
@click.option("--summary", "summary", default=None, help="Release summary (defaults to a generic one).")
def construct(
    project_path: str, output_dir: str, increment: str, answers_path: str | None, summary: str | None
) -> None:
    """Construct a temporary candidate Release: real Docker builds, a
    generated release.yaml, and every declared resource copied into the
    Contract-defined directory structure. Not yet validated or finalized.
    """
    try:
        data = construct_release(project_path, output_dir, increment, answers_path, summary)
    except PackagerError as exc:
        click.echo(render(failure("construct", exc)))
        sys.exit(1)
    click.echo(render(ok("construct", data)))


if __name__ == "__main__":
    main()
