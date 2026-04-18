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
    bus: str | None = typer.Option(
        None,
        "--bus",
        help="Scan a servo bus for responding IDs + limits. Format: "
        "`<protocol>:<port>[:<baud>]` (e.g. `feetech:/dev/ttyACM0` or "
        "`feetech:/dev/ttyACM0:1000000`). Emits a kinematics[] block "
        "to stdout. Requires the port to be free.",
    ),
) -> None:
    """Scan visible hardware and emit a draft ROBOT.md.

    Linux-only. Covers PCI (via lspci), USB (via lsusb), /dev/tty[ACM|USB]*,
    cameras (depthai + v4l2), and runtime info. Emitted draft has TODO
    markers for identity fields — review before committing. Always run
    `robot-md validate` afterwards.

    With `--bus <protocol>:<port>`, also pings every ID on a servo bus
    (Tier B) and emits a populated `physics.kinematics[]` block with
    discovered servo IDs + limits. Today: `feetech` only.
    """
    if bus:
        parts = bus.split(":", 2)
        if len(parts) < 2 or parts[0] != "feetech":
            err_console.print(
                "[red]✗[/red] --bus requires format `feetech:<port>[:<baud>]`; "
                f"got {bus!r}. Only `feetech` is supported today."
            )
            raise typer.Exit(code=2)
        port = parts[1]
        baud = int(parts[2]) if len(parts) == 3 else 1_000_000

        try:
            from robot_md.bus_scan import render_bus_scan_as_yaml, scan_feetech

            servos = scan_feetech(port, baud=baud)
        except RuntimeError as e:
            err_console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(code=2) from None
        out_console.print(
            f"[green]✓[/green] {len(servos)} servo(s) responding on {port} @ {baud} baud"
        )
        sys.stdout.write(render_bus_scan_as_yaml(servos))
        return

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
    preset: str | None = typer.Option(
        None,
        "--preset",
        "-p",
        help="Force a specific preset (e.g. so-arm101, turtlebot4, picar-x).",
    ),
    wizard_mode: bool = typer.Option(
        False, "--wizard", help="Interactive 7-step walk-through (default is zero prompts)."
    ),
    do_register: bool = typer.Option(
        False,
        "--register",
        help=(
            "After writing the draft, validate + POST to rcan.dev to mint "
            "an RRN. One-command complete setup."
        ),
    ),
    contact_email: str | None = typer.Option(
        None,
        "--contact-email",
        help="Contact email sent with --register. Falls back to metadata.author.",
    ),
    manufacturer: str | None = typer.Option(
        None,
        "--manufacturer",
        help="Override manufacturer when --register. Otherwise read from preset/manifest.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override model when --register. Otherwise the preset name (e.g. 'so-arm101').",
    ),
    version_: str | None = typer.Option(
        None,
        "--version-",
        help="Override version when --register. Otherwise '1.0'.",
    ),
    device_id: str | None = typer.Option(
        None,
        "--device-id",
        help="Override device_id when --register. Otherwise the robot_name.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing ROBOT.md."),
    list_presets: bool = typer.Option(
        False, "--list-presets", help="Print available presets and exit."
    ),
    with_claude_md: bool = typer.Option(
        True,
        "--with-claude-md/--no-claude-md",
        help=(
            "Also generate a CLAUDE.md next to the manifest so Claude Code "
            "auto-recognizes the robot (default: on; safe — appends rather "
            "than overwrites if CLAUDE.md already exists)."
        ),
    ),
) -> None:
    """Zero-to-registered-ROBOT.md in one command.

    Default is *super-duper-quick*: no prompts. Scans hardware, matches a
    preset from the built-in library, writes a validated draft.

    Add `--register` to ALSO mint an RRN on the Robot Registry Foundation
    (`rcan.dev/api/v1/robots`) in the same breath — a one-line complete
    setup with no OpenCastor or other runtime dependency:

      robot-md init my-bob --preset so-arm101 --register --contact-email me@co.com

    Outputs at the end the `claude mcp add` snippet so the operator can
    hand the manifest to any MCP-aware agent (Claude Code, Cursor, Zed,
    Gemini CLI, …) with one more paste.

    Examples:

      robot-md init                                          # zero prompts, draft only
      robot-md init my-bob                                   # pick a name
      robot-md init --preset so-arm101 my-bob                # force a preset
      robot-md init --wizard                                 # interactive
      robot-md init my-bob -p so-arm101 --register \\
          --contact-email me@co.com                           # ← full setup, one line
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

    # --register: run validate + register after the draft lands
    if do_register:
        # Validate first — mint fails if the manifest is malformed, better
        # to catch it here with a clear error than get an HTTP 4xx.
        try:
            parsed = parse_file(out)
        except ParseError as e:
            err_console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(code=FILE_ERROR) from None
        result = validate_parsed(parsed)
        if result.code != VALID:
            err_console.print(
                f"[red]✗[/red] draft failed validation before register — {result.summary}"
            )
            for msg in result.errors:
                err_console.print(f"  - {msg}")
            raise typer.Exit(code=result.code)
        out_console.print(f"[green]✓[/green] {result.summary}")

        # Apply --manufacturer/--model/--version-/--device-id overrides to
        # the manifest BEFORE register runs, so the manifest is self-
        # consistent with what gets POSTed to RRF. Without this, the mint
        # request uses the flag values but the manifest keeps preset defaults.
        overrides = {
            "manufacturer": manufacturer,
            "model": model,
            "version": version_,
            "device_id": device_id,
        }
        if any(v is not None for v in overrides.values()):
            from ruamel.yaml import YAML

            text = out.read_text()
            end = text.find("\n---", 3)
            fm_text = text[3:end].lstrip("\n")
            body_text = text[end + 4 :]
            y = YAML()
            y.preserve_quotes = True
            y.indent(mapping=2, sequence=4, offset=2)
            data = y.load(fm_text)
            meta = data.setdefault("metadata", {})
            for k, v in overrides.items():
                if v is not None:
                    meta[k] = v
            import io

            buf = io.StringIO()
            y.dump(data, buf)
            out.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)

        from robot_md.register import cli_register

        rc = cli_register(
            str(out),
            manufacturer=manufacturer,
            model=model,
            version=version_,
            device_id=device_id,
            contact_email=contact_email,
        )
        if rc != 0:
            raise typer.Exit(code=rc)

        # Final: print the MCP one-liner
        out_console.print("\n[bold]Next — hand your manifest to Claude Code:[/bold]")
        out_console.print(f'  claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/{out.name}"')

    # Optionally generate a CLAUDE.md so the agent harness recognizes the
    # robot without the operator having to run a second command. Safe by
    # construction: `apply_to_file` appends rather than overwrites if
    # CLAUDE.md already exists.
    if with_claude_md:
        from robot_md.claude_md import apply_to_file, render_claude_md

        claude_md_path = out.parent / "CLAUDE.md"
        try:
            rendered = render_claude_md(out)
        except (ParseError, FileNotFoundError) as e:
            err_console.print(
                f"[yellow]⚠[/yellow] could not generate CLAUDE.md: {e} "
                f"(manifest itself was written OK)"
            )
        else:
            action = apply_to_file(rendered, claude_md_path)
            verb = {
                "wrote": "wrote",
                "appended": "appended robot-md block to",
                "updated": "updated robot-md block in",
                "overwrote": "overwrote",
            }.get(action, action)
            out_console.print(f"[green]✓[/green] {verb} {claude_md_path}")


@app.command()
def register(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    endpoint: str = typer.Option(
        "https://rcan.dev/api/v1/robots",
        "--endpoint",
        help="RRF mint endpoint. Override for staging / self-hosted.",
    ),
    manufacturer: str | None = typer.Option(None, "--manufacturer"),
    model: str | None = typer.Option(None, "--model"),
    version: str | None = typer.Option(None, "--version"),
    device_id: str | None = typer.Option(None, "--device-id"),
    description: str | None = typer.Option(None, "--description"),
    contact_email: str | None = typer.Option(None, "--contact-email"),
    source: str | None = typer.Option(None, "--source"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print request body, don't POST."),
) -> None:
    """Mint an RRN for this robot against the Robot Registry Foundation.

    Resolves manufacturer/model/version/device_id from the manifest's
    `metadata` block, or from CLI flags if you want to override. POSTs to
    the live RRF mint endpoint and writes the assigned RRN back into the
    manifest. Issued API keys are saved to `~/.robot-md/keys/<rrn>.apikey`
    with mode 600 — never printed.

    Example:

      robot-md register ROBOT.md
      robot-md register ROBOT.md --contact-email me@example.com
      robot-md register ROBOT.md --dry-run

    The live endpoint currently speaks the v0.1.x unsigned shape. Signed
    registration with key-binding at mint time (v0.2 §9.1) will ship as an
    additive `--signed` flag on this same command once the server-side
    endpoint lands.
    """
    from robot_md.register import cli_register

    rc = cli_register(
        str(path),
        endpoint=endpoint,
        manufacturer=manufacturer,
        model=model,
        version=version,
        device_id=device_id,
        description=description,
        contact_email=contact_email,
        source=source,
        dry_run=dry_run,
    )
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command()
def unregister(
    rrn: str = typer.Argument(..., help="The RRN to delete (e.g. RRN-000000000042)."),
    endpoint: str = typer.Option(
        "https://rcan.dev/api/v1/robots",
        "--endpoint",
        help="RRF base endpoint. Override for staging / self-hosted.",
    ),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="API key for this RRN. Default: read from ~/.robot-md/keys/<rrn>.apikey.",
    ),
) -> None:
    """Delete a robot from the Robot Registry Foundation.

    Uses the issued API key (stored by `robot-md register` at
    `~/.robot-md/keys/<rrn>.apikey`) to authorize the DELETE against
    `rcan.dev/api/v1/robots/<rrn>`. The local key file is removed after
    a successful delete. Does NOT modify any local ROBOT.md files — if
    you want to un-publish + clean the manifest, edit metadata.rrn to
    empty string after this returns.

    Examples:

      robot-md unregister RRN-000000000042
      robot-md unregister RRN-000000000042 --api-key "$(cat old.apikey)"
    """
    from robot_md.register import cli_unregister

    rc = cli_unregister(rrn, endpoint=endpoint, api_key=api_key)
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command()
def doctor(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Target a specific ROBOT.md file (default: ./ROBOT.md if present).",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero on warnings as well as failures."
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit results as JSON instead of a rich table."
    ),
) -> None:
    """Diagnose the local environment + manifest.

    Runs five buckets of checks: install (CLI + deps), manifest (parse + schema),
    network (registry reachable + RRN resolvable), drivers (serial/TCP probe per
    declared driver), and keystore (API key file permissions).

    Never writes files, never mutates servos, never hits registry write
    endpoints. Safe to run anywhere, anytime.

    Examples:

      robot-md doctor                          # check ./ROBOT.md + env
      robot-md doctor --path examples/bob.ROBOT.md
      robot-md doctor --strict --json          # CI-friendly
    """
    from robot_md.doctor import counts, exit_code, run_all

    results = run_all(path)
    c = counts(results)

    if json_out:
        import json

        payload = {
            "version": __version__,
            "summary": c,
            "checks": [
                {"name": r.name, "bucket": r.bucket, "status": r.status, "detail": r.detail}
                for r in results
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        from rich.table import Table

        table = Table(title="robot-md doctor", show_lines=False)
        table.add_column("Bucket", style="dim", no_wrap=True)
        table.add_column("Check", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Detail")
        glyph = {
            "pass": "[green]✓[/green]",
            "warn": "[yellow]⚠[/yellow]",
            "fail": "[red]✗[/red]",
            "skip": "[dim]—[/dim]",
        }
        for r in results:
            table.add_row(r.bucket, r.name, glyph.get(r.status, r.status), r.detail)
        out_console.print(table)
        out_console.print(
            f"  [green]{c['pass']} pass[/green]  "
            f"[yellow]{c['warn']} warn[/yellow]  "
            f"[red]{c['fail']} fail[/red]  "
            f"[dim]{c['skip']} skip[/dim]"
        )

    raise typer.Exit(code=exit_code(results, strict))


@app.command("claude-md")
def claude_md_cmd(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    out: Path = typer.Option(
        Path("CLAUDE.md"),
        "--out",
        "-o",
        help="Output path for the generated CLAUDE.md.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite the entire file (default is to append/update in place).",
    ),
    stdout: bool = typer.Option(
        False, "--stdout", help="Print to stdout instead of writing a file."
    ),
) -> None:
    """Generate a `CLAUDE.md` for this robot's project directory.

    The file teaches Claude Code (and any CLAUDE.md-aware agent harness)
    how to recognize robot-related intent and which `robot-md` verbs to
    dispatch. Drop it next to `ROBOT.md` and Claude reads it at session
    start.

    The generated file is pre-filled from your manifest: robot name, RRN,
    HITL gates, primary driver. Operator-specific TODOs remain for you
    to customize (host machine notes, project conventions).

    Merge semantics (default):

    \b
      - CLAUDE.md does not exist       → write it with sentinels.
      - CLAUDE.md exists, no sentinels → APPEND our block at the end.
      - CLAUDE.md exists, has sentinels → UPDATE the delimited block in place
                                           (operator content above/below is
                                           preserved).
      - --force                        → overwrite the entire file.

    Examples:

      robot-md claude-md ROBOT.md                    # writes ./CLAUDE.md
      robot-md claude-md ROBOT.md --out docs/CLAUDE.md
      robot-md claude-md ROBOT.md --stdout | less    # preview only
      robot-md claude-md ROBOT.md --force            # blow away existing content
    """
    from robot_md.claude_md import apply_to_file, render_claude_md

    try:
        rendered = render_claude_md(path)
    except ParseError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    except FileNotFoundError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    if stdout:
        sys.stdout.write(rendered)
        return

    action = apply_to_file(rendered, out, force=force)
    verb = {
        "wrote": "wrote",
        "appended": "appended robot-md block to",
        "updated": "updated robot-md block in",
        "overwrote": "overwrote",
    }.get(action, action)
    out_console.print(f"[green]✓[/green] {verb} {out}")
    out_console.print(
        "  Claude Code will read this file at session start. Review the TODOs "
        "and customize per-project conventions."
    )


@app.command("install-skill")
def install_skill_cmd(
    dest: Path | None = typer.Option(
        None,
        "--dest",
        help="Skills directory (default: ~/.claude/skills).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite an existing using-robot-md/SKILL.md.",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print the skill to stdout instead of installing it.",
    ),
) -> None:
    """Install the `using-robot-md` skill into your Claude Code skills dir.

    The skill teaches skill-aware harnesses (superpowers, etc.) to
    auto-invoke robot-md tooling when the operator's message mentions the
    robot, its capabilities, safety, or any `robot-md` verb. Writes to
    `~/.claude/skills/using-robot-md/SKILL.md` by default.

    Examples:

    \b
      robot-md install-skill                       # writes to ~/.claude/skills/
      robot-md install-skill --dest ./skills       # project-local skills dir
      robot-md install-skill --force               # overwrite existing
      robot-md install-skill --stdout | less       # preview the skill
    """
    from robot_md.skill import install, skill_content

    try:
        content = skill_content()
    except FileNotFoundError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    if stdout:
        sys.stdout.write(content)
        return

    try:
        written = install(dest, force=force)
    except FileExistsError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    out_console.print(f"[green]✓[/green] installed {written}")
    out_console.print(
        "  Claude Code (with superpowers or any skill-aware harness) will "
        "auto-invoke this skill when the operator mentions the robot."
    )


@app.command("publish-discovery")
def publish_discovery(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    url: str = typer.Option(
        ...,
        "--url",
        help="Absolute URL at which the manifest will be served (http[s]://...).",
    ),
    out: Path = typer.Option(
        Path(".well-known/robot-md.json"),
        "--out",
        "-o",
        help="Output path for the discovery JSON document.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite an existing discovery file."
    ),
) -> None:
    """Emit a `.well-known/robot-md.json` discovery document.

    The discovery document lets MCP clients, crawlers, and federated
    registries locate the manifest without prior configuration. Copy the
    emitted file into the `.well-known/` directory of the robot's web
    server (or any HTTP-reachable sidecar).

    The document includes the manifest URL, RRN (if present), SHA-256
    digest of the served manifest, and a derived public resolver URL.
    See spec §6.1 for the full schema.

    Examples:

      robot-md publish-discovery ROBOT.md --url https://bob.local/ROBOT.md
      robot-md publish-discovery ROBOT.md --url https://bob.local/ROBOT.md \\
          --out /var/www/.well-known/robot-md.json
    """
    from robot_md.discovery import build_discovery, write_discovery

    if out.exists() and not force:
        err_console.print(f"[red]✗[/red] {out} already exists — pass --force to overwrite")
        raise typer.Exit(code=FILE_ERROR)

    try:
        doc = build_discovery(path, url)
    except (FileNotFoundError, ValueError, ParseError) as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    write_discovery(doc, out)
    out_console.print(f"[green]✓[/green] wrote {out}")
    out_console.print(f"  serve it at: {url.rsplit('/', 1)[0]}/.well-known/robot-md.json")
    if doc.get("rrn"):
        out_console.print(f"  rrn: {doc['rrn']}  resolver: {doc.get('public_resolver')}")


@app.command()
def calibrate(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    zero: bool = typer.Option(
        False, "--zero", help="Record current encoder positions as zero_pose_steps for every joint."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Per-joint: command a small test move, ask operator for direction, set encoder_sign.",
    ),
    hand_eye: bool = typer.Option(
        False,
        "--hand-eye",
        help="ArUco-based camera-to-arm-base extrinsic via OAK-D + a printed marker.",
    ),
    marker_pos: str | None = typer.Option(
        None,
        "--marker-pos",
        help="`x,y,z` in mm — center of the ArUco marker in arm-base frame.",
    ),
    marker_size: float = typer.Option(
        50.0, "--marker-size", help="Marker side length in mm (default: 50)."
    ),
    marker_id: int = typer.Option(0, "--marker-id", help="ArUco id (DICT_4X4_50) — default 0."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Read encoders / detect marker and print result; do not rewrite the manifest.",
    ),
) -> None:
    """Populate kinematic-solver physical fields that can't be autodetected.

    Modes:
      --zero       Interactive: pose arm in the declared zero config, press
                   Enter, we record current encoders as `zero_pose_steps`
                   for every joint in `physics.kinematics[]`.
      --sign       Per-joint: command a small test move (+~80 steps), ask
                   operator whether it moved in the positive-convention
                   direction, record `encoder_sign` (+1 or -1) accordingly.
                   Each joint is restored to its original position after.

    Future:
      --hand-eye   ArUco-based camera-to-arm-base extrinsic, writes
                   `physics.solver.camera.extrinsic`. (Task #44 follow-up.)

    Prerequisite: the arm's serial port must be free — stop any gateway that
    is holding it first (for OpenCastor: `sudo systemctl stop castor-gateway`).
    """
    from robot_md.calibrate import cli_calibrate_sign, cli_calibrate_zero

    if not (zero or sign or hand_eye):
        err_console.print(
            "[yellow]calibrate: pick a mode — --zero, --sign, or --hand-eye.[/yellow]\n"
            "  robot-md calibrate --zero ROBOT.md\n"
            "  robot-md calibrate --sign ROBOT.md\n"
            "  robot-md calibrate --hand-eye --marker-pos 300,0,0 ROBOT.md"
        )
        raise typer.Exit(code=2)

    rc = 0
    if zero:
        rc = cli_calibrate_zero(str(path), dry_run=dry_run)
        if rc != 0:
            raise typer.Exit(code=rc)
    if sign:
        rc = cli_calibrate_sign(str(path))
        if rc != 0:
            raise typer.Exit(code=rc)
    if hand_eye:
        if not marker_pos:
            err_console.print(
                "[red]✗[/red] --hand-eye requires --marker-pos x,y,z (mm in arm-base frame)."
            )
            raise typer.Exit(code=2)
        try:
            xyz = tuple(float(v.strip()) for v in marker_pos.split(","))
            if len(xyz) != 3:
                raise ValueError
        except ValueError:
            err_console.print(
                f"[red]✗[/red] --marker-pos must be `x,y,z` (three floats), got {marker_pos!r}"
            )
            raise typer.Exit(code=2) from None
        from robot_md.hand_eye import cli_calibrate_hand_eye

        rc = cli_calibrate_hand_eye(
            str(path),
            marker_pos=xyz,
            marker_size_mm=marker_size,
            marker_id=marker_id,
            dry_run=dry_run,
        )
        if rc != 0:
            raise typer.Exit(code=rc)


if __name__ == "__main__":
    app()
