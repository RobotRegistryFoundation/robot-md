"""robot-md CLI entry point — typer-based."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from robot_md import __version__
from robot_md.context import emit_context
from robot_md.parser import ParseError, parse_file
from robot_md.render import render_yaml
from robot_md.validate import (
    FILE_ERROR,
    MISSING_BODY_SECTION,
    RCAN_CONFORMANCE_VIOLATION,
    SCHEMA_VIOLATION,
    VALID,
)
from robot_md.validate import (
    validate as validate_parsed,
)

app = typer.Typer(
    name="robot-md",
    help="Parse, validate, and render ROBOT.md files.",
    no_args_is_help=True,
    add_completion=False,
)
err_console = Console(stderr=True)
out_console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"robot-md {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


@app.command()
def validate(path: Path = typer.Argument(..., help="Path to a ROBOT.md file.")) -> None:
    """Validate a ROBOT.md file against schema + body requirements."""
    try:
        parsed = parse_file(path)
    except ParseError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    result = validate_parsed(parsed)
    if result.code == VALID:
        out_console.print(f"[green]✓[/green] {result.summary}")
        raise typer.Exit(code=VALID)

    severity = {
        SCHEMA_VIOLATION: ("schema violation", "red"),
        RCAN_CONFORMANCE_VIOLATION: ("RCAN conformance violation", "red"),
        MISSING_BODY_SECTION: ("missing body section", "yellow"),
    }.get(result.code, (f"error (code {result.code})", "red"))

    err_console.print(f"[{severity[1]}]✗ {severity[0]}[/{severity[1]}]")
    for msg in result.errors:
        err_console.print(f"  - {msg}")
    raise typer.Exit(code=result.code)


@app.command()
def render(path: Path = typer.Argument(..., help="Path to a ROBOT.md file.")) -> None:
    """Strip the prose body and emit the frontmatter as pure YAML to stdout."""
    try:
        parsed = parse_file(path)
    except ParseError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    sys.stdout.write(render_yaml(parsed))


@app.command()
def context(path: Path = typer.Argument(..., help="Path to a ROBOT.md file.")) -> None:
    """Emit a Claude-ready context block (markdown) to stdout."""
    try:
        parsed = parse_file(path)
    except ParseError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    sys.stdout.write(emit_context(parsed))


if __name__ == "__main__":
    app()
