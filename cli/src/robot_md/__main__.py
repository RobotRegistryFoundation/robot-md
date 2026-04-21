"""robot-md CLI entry point — typer-based."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import typer
from rich.console import Console

from robot_md import __version__
from robot_md.autodetect import emit_draft, scan_system
from robot_md.context import emit_context
from robot_md.init_phases import phase_calibrate_extrinsic
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
        False,
        "--wizard",
        help="(Deprecated alias for the default interactive flow; kept for compat.)",
    ),
    do_register: bool = typer.Option(
        False,
        "--register",
        help="Mint an RRN on rcan.dev as part of setup.",
    ),
    contact_email: str | None = typer.Option(
        None, "--contact-email", help="Contact email for --register."
    ),
    manufacturer: str | None = typer.Option(None, "--manufacturer"),
    model: str | None = typer.Option(None, "--model"),
    version_: str | None = typer.Option(None, "--version-"),
    device_id: str | None = typer.Option(None, "--device-id"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite an existing ROBOT.md."),
    list_presets: bool = typer.Option(
        False, "--list-presets", help="Print available presets and exit."
    ),
    with_claude_md: bool = typer.Option(
        True,
        "--with-claude-md/--no-claude-md",
        help="Also generate a CLAUDE.md next to the manifest.",
    ),
    no_install_mcp: bool = typer.Option(
        False, "--no-install-mcp", help="Skip the Claude Code MCP registration step."
    ),
    no_install_skill: bool = typer.Option(
        False, "--no-install-skill", help="Skip the using-robot-md skill install step."
    ),
    no_sign: bool = typer.Option(
        False, "--no-sign", help="Skip encoder-sign calibration (still run zero-cal)."
    ),
    no_calibrate: bool = typer.Option(
        False, "--no-calibrate", help="Skip BOTH sign and zero calibration."
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Manifest only — implies --no-install-mcp, --no-install-skill, --no-calibrate. "
        "For scripted callers / CI.",
    ),
) -> None:
    """Zero-to-actuatable-ROBOT.md in one command.

    Default flow walks six phases: write manifest → (register) → install MCP
    with Claude Code → install skill → prompt + sign-cal → prompt + zero-cal.
    Headless (no-TTY) callers auto-skip the calibration phases.

    Examples:

      robot-md init                          # zero prompts on headless, full flow on TTY
      robot-md init bob --preset so-arm101               # explicit name + preset
      robot-md init bob --preset so-arm101 --register \\
          --contact-email me@acme.com                    # + mint RRN
      robot-md init bob --preset so-arm101 --non-interactive   # scripted / CI
    """
    from robot_md.init import default_flow, load_presets

    if list_presets:
        presets = load_presets()
        for p in presets:
            typer.echo(f"  {p.display_name:<24}{p.data.get('physics', {}).get('type', '')}")
        raise typer.Exit()

    if wizard_mode:
        typer.echo(
            "note: --wizard is now an alias for the default flow. You can drop the flag.",
            err=True,
        )

    if non_interactive:
        no_install_mcp = True
        no_install_skill = True
        no_calibrate = True

    rc = default_flow(
        out,
        robot_name=name,
        preset_name=preset,
        force=force,
        do_register=do_register,
        contact_email=contact_email,
        manufacturer=manufacturer,
        model=model,
        version_=version_,
        device_id=device_id,
        do_install_mcp=not no_install_mcp,
        do_install_skill=not no_install_skill,
        do_sign_cal=not (no_calibrate or no_sign),
        do_zero_cal=not no_calibrate,
        do_refresh_claude_md=with_claude_md,
    )

    if rc != 0:
        raise typer.Exit(code=rc)


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


def _hardware_present() -> bool:
    """Heuristic: return True if any /dev/ttyACM* device is visible.

    Used by ``--hardware auto`` to decide whether to attempt hardware checks.
    Conservative by design — only triggers when a serial device is plugged in;
    does not probe USB or depthai directly. This keeps doctor side-effect-free
    on machines without hardware attached.
    """
    import glob as _glob

    return bool(_glob.glob("/dev/ttyACM*"))


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
    hardware: str = typer.Option(
        "auto",
        "--hardware",
        help="Hardware checks: auto | on | off. "
        "auto runs checks when /dev/ttyACM* is present; "
        "on forces checks even without detected hardware; "
        "off skips hardware checks entirely.",
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
    from robot_md.doctor import CheckResult, counts, exit_code, run_all

    results = run_all(path)

    # Optional hardware checks — converted to CheckResult so they appear in
    # both the rich table and --json output.
    should_hw = hardware == "on" or (hardware == "auto" and _hardware_present())
    if should_hw:
        try:
            from robot_md.backends.feetech_depthai.doctor import hw_checks
            from robot_md.backends.feetech_depthai.perception import Perception
            from robot_md.backends.feetech_depthai.servo import ServoBus
            from robot_md.parser import parse_file as _parse_file
            from robot_md.robot_spec import RobotSpec

            if path is None:
                results.append(
                    CheckResult(
                        "hardware checks",
                        "hardware",
                        "skip",
                        "no manifest path — pass --path to enable",
                    )
                )
            else:
                spec = RobotSpec.from_parsed(_parse_file(path))
                expected_ids = {
                    j["id"] for j in spec.physics.kinematics if isinstance(j, dict) and "id" in j
                }
                bus = ServoBus.from_spec(spec)
                cam = Perception.from_spec(spec)
                bus.open()
                try:
                    hw = hw_checks(bus=bus, camera=cam, expected_servo_ids=expected_ids)
                    for c_hw in hw:
                        # Map hw Check status to doctor CheckResult status:
                        # "info" maps to "skip" (non-actionable), rest pass through.
                        doctor_status = c_hw.status if c_hw.status != "info" else "skip"
                        results.append(
                            CheckResult(c_hw.name, "hardware", doctor_status, c_hw.message)
                        )
                finally:
                    bus.close()
        except Exception as e:
            results.append(CheckResult("hardware checks", "hardware", "skip", f"skipped: {e}"))

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


@app.command("install-desktop")
def install_desktop_cmd(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    config: Path | None = typer.Option(
        None,
        "--config",
        help=(
            "Override the Claude Desktop config path (default: the OS-appropriate "
            "`claude_desktop_config.json` — macOS ~/Library/Application Support/"
            "Claude/, Windows %APPDATA%/Claude/, Linux ~/.config/Claude/)."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Replace an existing robot-md entry if it differs from the computed one.",
    ),
) -> None:
    """Wire ROBOT.md into the Claude Desktop (macOS/Windows) app.

    Merge-adds a `robot-md` entry under `mcpServers` in the Claude
    Desktop config file, preserving any other servers already declared
    (filesystem, github, etc.). The entry runs:

    \b
      npx -y robot-md-mcp <absolute-path-to-ROBOT.md>

    via stdio. No global install needed — npx pulls the latest
    `robot-md-mcp` wheel on first launch and caches it.

    After install, restart Claude Desktop. Then ask Claude: "What can
    this robot do?" — it'll route to `robot-md://<name>/capabilities`
    via the server's intent-matchable descriptions.

    Examples:

    \b
      robot-md install-desktop ROBOT.md                 # merge into default config
      robot-md install-desktop ROBOT.md --force         # replace existing robot-md entry
      robot-md install-desktop ROBOT.md --config ./cfg  # custom config path (testing)
    """
    from robot_md.install_desktop import default_config_path, install

    try:
        result = install(path, config_path=config, force=force)
    except FileNotFoundError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    except ValueError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    cfg_path = config or default_config_path()
    if result.status == "conflict":
        err_console.print(
            f"[yellow]⚠[/yellow] {cfg_path} already has a `robot-md` entry that differs "
            f"from what I would write. Pass --force to overwrite.\n"
            f"  existing: {result.prior_entry}"
        )
        raise typer.Exit(code=1)

    verb = {
        "wrote": "wrote new config",
        "added": "added `robot-md` entry to",
        "updated": "updated `robot-md` entry in",
        "unchanged": "already up to date in",
    }.get(result.status, result.status)
    out_console.print(f"[green]✓[/green] {verb} {result.path}")
    out_console.print(
        "  Restart Claude Desktop for the change to take effect. Then ask "
        'Claude: "What can this robot do?"'
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
    extrinsic: bool = typer.Option(
        False,
        "--extrinsic",
        help="Calibrate camera-to-arm extrinsic via gripper silhouette.",
    ),
    hand_eye: bool = typer.Option(
        False,
        "--hand-eye",
        hidden=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Read encoders and print result; do not rewrite the manifest.",
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
      --extrinsic  Gripper-silhouette-based camera-to-arm extrinsic, writes
                   `physics.solver.cameras[0].extrinsic`.

    Prerequisite: the arm's serial port must be free — stop any gateway that
    is holding it first (for OpenCastor: `sudo systemctl stop castor-gateway`).
    """
    from robot_md.calibrate import cli_calibrate_sign, cli_calibrate_zero

    if hand_eye:
        typer.echo("warning: --hand-eye is deprecated; use --extrinsic (removed in v0.8)", err=True)
        extrinsic = True

    if not (zero or sign or extrinsic):
        err_console.print(
            "[yellow]calibrate: pick a mode — --zero, --sign, or --extrinsic.[/yellow]\n"
            "  robot-md calibrate --zero ROBOT.md\n"
            "  robot-md calibrate --sign ROBOT.md\n"
            "  robot-md calibrate --extrinsic ROBOT.md"
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
    if extrinsic:
        bus = None
        cam = None
        try:
            from robot_md.backends.feetech_depthai.perception import Perception
            from robot_md.backends.feetech_depthai.servo import ServoBus
            from robot_md.parser import parse_file
            from robot_md.robot_spec import RobotSpec

            spec = RobotSpec.from_parsed(parse_file(path))
            try:
                bus = ServoBus.from_spec(spec)
                bus.open()
            except Exception as e:
                typer.echo(f"could not open servo bus: {e}", err=True)
                bus = None
            try:
                cam = Perception.from_spec(spec)
                cam.open()
            except Exception as e:
                typer.echo(f"could not open camera: {e}", err=True)
                cam = None
        except Exception as e:
            typer.echo(f"could not load manifest: {e}", err=True)
        result = phase_calibrate_extrinsic(path, bus=bus, camera=cam, interactive=True)
        typer.echo(result.message)
        if bus is not None:
            with contextlib.suppress(Exception):
                bus.close()
        if cam is not None:
            with contextlib.suppress(Exception):
                cam.close()
        raise typer.Exit(0 if result.status in ("ok", "skipped") else 1)


@app.command("calibrate-intrinsic")
def calibrate_intrinsic_cmd(
    manifest: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    driver: str = typer.Option(..., help="drivers[].id of the camera."),
    stream: str = typer.Option(..., help="Stream name (rgb, left, right, ...)."),
    session_file: Path = typer.Option(
        Path("intrinsic.session.json"),
        help="Session-state file (JSON).",
    ),
    frame: Path | None = typer.Option(None, help="Add a captured frame."),
    finalize: bool = typer.Option(False, help="Solve + write intrinsic back."),
) -> None:
    """Checkerboard intrinsic calibration — session-file driven."""
    from robot_md.calibrate_intrinsic import (
        session_add_frame,
        session_finalize,
        session_init,
    )

    if finalize:
        session_finalize(session_file=session_file, robot_md_file=manifest)
        typer.echo(f"✓ intrinsic written to {manifest}")
        return
    if frame is not None:
        session_add_frame(session_file=session_file, frame_path=frame)
        typer.echo(f"✓ added frame {frame}")
        return
    session_init(session_file=session_file, driver_id=driver, stream=stream, board_size=(9, 6))
    typer.echo(f"✓ session at {session_file}; print the checkerboard PNG next to it")


@app.command()
def mcp(
    manifest: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
) -> None:
    """Start the robot-md MCP server over stdio (same as `robot-md-mcp`)."""
    import sys as _sys

    from robot_md.mcp.server import main as _mcp_main

    _sys.argv = ["robot-md-mcp", str(manifest)]
    raise typer.Exit(code=_mcp_main())


pose_app = typer.Typer(help="Teach and manage named arm poses.", no_args_is_help=True)
app.add_typer(pose_app, name="pose")


def _open_feetech_bus(manifest_path: Path):
    """Resolve the Feetech servo bus for the manifest. Overridable in tests."""
    from robot_md.mcp.context import load_context

    ctx = load_context(manifest_path)
    bus = getattr(ctx.backend, "_servo_bus", None)
    if bus is None:
        raise RuntimeError("no feetech servo bus available for this manifest")
    return bus


@pose_app.command("teach")
def pose_teach(
    name: str = typer.Argument(..., help="Pose name, e.g. 'ready' or 'stowed'."),
    path: Path = typer.Argument(..., help="Path to ROBOT.md"),
    description: str | None = typer.Option(None, "--description", "-d"),
    yes: bool = typer.Option(False, "--yes", help="Skip the interactive prompt."),
):
    """Record the arm's current joint positions under physics.poses[name].

    Torques off the servos, reads every joint, writes to the manifest, and
    re-torques. The operator is expected to have physically posed the arm
    before invoking.
    """
    from robot_md.poses import teach_pose

    if not yes:
        typer.confirm(
            f"Torque will release so you can pose the arm. Ready to teach '{name}'?",
            abort=True,
        )
    bus = _open_feetech_bus(path)
    joints = teach_pose(bus, path, name=name, description=description)
    typer.echo(f"✓ wrote physics.poses.{name} ({len(joints)} joints)")


@pose_app.command("list")
def pose_list(path: Path = typer.Argument(..., help="Path to ROBOT.md")):
    """List named poses declared in the manifest."""
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parse_file(path))
    if not spec.physics.poses:
        typer.echo("(no poses declared)")
        return
    for name, pose in spec.physics.poses.items():
        desc = f" — {pose.description}" if pose.description else ""
        typer.echo(f"  {name} ({pose.source or 'declared'}, {len(pose.joints)} joints){desc}")


dashboard_app = typer.Typer(help="Dev dashboard for robot-md.", no_args_is_help=True)
app.add_typer(dashboard_app, name="dashboard")


@dashboard_app.command("serve")
def dashboard_serve(
    manifest: Path | None = typer.Option(None, help="Optional ROBOT.md; warnings shown in header."),
    host: str = typer.Option("127.0.0.1", help="Bind host (keep local)."),
    port: int = typer.Option(8091, help="Bind port."),
) -> None:
    """Start the dev dashboard at http://<host>:<port>."""
    import uvicorn

    from robot_md.dashboard.server import build_app

    app_ = build_app(manifest=manifest)
    typer.echo(f"dashboard: http://{host}:{port}")
    uvicorn.run(app_, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
