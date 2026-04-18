"""robot-md CLI entry point — typer-based."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from robot_md import __version__
from robot_md.autodetect import emit_draft, scan_system
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


@app.command()
def autodetect(
    write: Path | None = typer.Option(
        None,
        "--write",
        "-w",
        help="Write draft to this path (refuses to overwrite). If omitted, prints to stdout.",
    ),
) -> None:
    """Scan visible hardware and emit a draft ROBOT.md.

    Linux-only. Covers PCI (via lspci), USB (via lsusb), /dev/tty[ACM|USB]*,
    and runtime info. Emitted draft has TODO markers for identity fields —
    review before committing. Always run `robot-md validate` afterwards.
    """
    scan = scan_system()
    draft = emit_draft(scan)
    if write is None:
        sys.stdout.write(draft)
        return
    if write.exists():
        err_console.print(f"[red]✗[/red] {write} already exists — refusing to overwrite")
        raise typer.Exit(code=FILE_ERROR)
    write.write_text(draft)
    out_console.print(f"[green]✓[/green] wrote draft to {write}")
    out_console.print(f"  next: edit the TODOs, then `robot-md validate {write}`")


@app.command()
def init(
    name: str | None = typer.Argument(None, help="Robot name. Defaults to `robot-<hostname>`."),
    out: Path = typer.Option(Path("./ROBOT.md"), "--out", "-o", help="Write draft to this path."),
    preset: str | None = typer.Option(None, "--preset", "-p", help="Force a specific preset (e.g. so-arm101, turtlebot4, picar-x)."),
    wizard_mode: bool = typer.Option(False, "--wizard", help="Interactive 7-step walk-through (default is zero prompts)."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing ROBOT.md."),
    list_presets: bool = typer.Option(False, "--list-presets", help="Print available presets and exit."),
) -> None:
    """Zero-to-ROBOT.md in one command.

    Default is *super-duper-quick*: no prompts. Scans hardware, matches a
    preset from the built-in library, writes a validated draft. Use
    `--wizard` for the interactive 7-step flow, or `--preset NAME` to
    force a known robot model.

    Examples:

      robot-md init                              # zero prompts
      robot-md init my-bob                       # pick a name
      robot-md init --preset so-arm101 my-bob    # force a preset
      robot-md init --wizard                     # interactive
    """
    from robot_md.init import load_presets, quick, wizard

    if list_presets:
        presets = load_presets()
        for p in presets:
            typer.echo(f"  {p.display_name:<24}{p.data.get('physics', {}).get('type', '')}")
        raise typer.Exit()

    if wizard_mode:
        rc = wizard(out, force=force)
    else:
        rc = quick(out, robot_name=name, preset_name=preset, force=force)
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command()
def calibrate(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    zero: bool = typer.Option(False, "--zero", help="Record current encoder positions as zero_pose_steps for every joint."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Read encoders and print them; do not rewrite the manifest."),
) -> None:
    """Populate kinematic-solver physical fields that can't be autodetected.

    Modes:
      --zero       Interactive: pose arm in the declared zero config, press
                   Enter, we record current encoders as `zero_pose_steps`
                   for every joint in `physics.kinematics[]`.

    Future (v1.1):
      --sign       Per-joint: command +N steps, ask operator which way the
                   joint moved, record `encoder_sign`.
      --hand-eye   ArUco-based camera-to-arm-base extrinsic, writes
                   `physics.solver.camera.extrinsic`.

    Prerequisite: the arm's serial port must be free — stop any gateway that
    is holding it first (for OpenCastor: `sudo systemctl stop castor-gateway`).
    """
    from robot_md.calibrate import cli_calibrate_zero

    if not zero:
        err_console.print(
            "[yellow]calibrate: pick a mode — currently only --zero is implemented.[/yellow]\n"
            "  robot-md calibrate --zero ROBOT.md"
        )
        raise typer.Exit(code=2)

    rc = cli_calibrate_zero(str(path), dry_run=dry_run)
    if rc != 0:
        raise typer.Exit(code=rc)


if __name__ == "__main__":
    app()
