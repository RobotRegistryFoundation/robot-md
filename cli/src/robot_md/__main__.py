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


@app.command("describe-capabilities")
def describe_capabilities(
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of human-readable text."
    ),
) -> None:
    """List capabilities exposed by every installed backend.

    Walks the entry-point group `robot_md.backends`, builds a BackendRegistry,
    and dumps Capability metadata grouped by backend + namespace.
    """
    import json as _json

    from robot_md.backends import BackendRegistry, enumerate_capabilities

    reg = BackendRegistry.from_entry_points()
    pairs = enumerate_capabilities(reg)

    by_backend: dict[str, list] = {}
    for backend_name, cap in pairs:
        by_backend.setdefault(backend_name, []).append(cap)

    if json_output:
        payload = [
            {
                "backend": backend_name,
                "capabilities": [
                    {
                        "name": c.name,
                        "namespace": c.namespace,
                        "arg_schema": c.arg_schema,
                        "description": c.description,
                    }
                    for c in caps
                ],
            }
            for backend_name, caps in sorted(by_backend.items())
        ]
        typer.echo(_json.dumps(payload, indent=2, sort_keys=True))
        return

    for backend_name in sorted(by_backend):
        typer.echo(f"\n{backend_name}")
        typer.echo("=" * len(backend_name))
        caps = by_backend[backend_name]
        core = [c for c in caps if c.namespace == "core"]
        vendor = [c for c in caps if c.namespace == "vendor"]
        if core:
            typer.echo("  core:")
            for c in sorted(core, key=lambda x: x.name):
                desc = f" — {c.description}" if c.description else ""
                typer.echo(f"    {c.name}{desc}")
        if vendor:
            typer.echo("  vendor:")
            for c in sorted(vendor, key=lambda x: x.name):
                desc = f" — {c.description}" if c.description else ""
                typer.echo(f"    {c.name}{desc}")


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
        help="Mint an RRN against the Robot Registry Foundation as part of setup.",
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
        False,
        "--no-install-mcp",
        help="(deprecated since 1.2.0; no-op — plugin handles MCP wiring)",
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

    Default flow walks five phases: write manifest → (register) → install
    skill → prompt + sign-cal → prompt + zero-cal.
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
    endpoint: str | None = typer.Option(
        None, "--endpoint", help="RRF mint endpoint. Override for staging / self-hosted."
    ),
    name: str | None = typer.Option(None, "--name"),
    manufacturer: str | None = typer.Option(None, "--manufacturer"),
    model: str | None = typer.Option(None, "--model"),
    firmware_version: str | None = typer.Option(None, "--firmware-version"),
    rcan_version: str | None = typer.Option(None, "--rcan-version"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Sign + print body, don't POST."),
) -> None:
    """Mint an RRN on Robot Registry Foundation with signed POST (RCAN 3.0)."""
    from robot_md.register import DEFAULT_ENDPOINT, cli_register

    rc = cli_register(
        path,
        endpoint=endpoint or DEFAULT_ENDPOINT,
        name=name,
        manufacturer=manufacturer,
        model=model,
        firmware_version=firmware_version,
        rcan_version=rcan_version,
        dry_run=dry_run,
    )
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command("emit-benchmarks")
def emit_benchmarks(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    iterations: int = typer.Option(
        20, "--iterations", "-n", help="Timed iterations per safety path (default: 20)."
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the artifact here. Default: print to stdout.",
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign with the v0.9.1 hybrid keypair from ~/.robot-md/keys/<rrn>.signing.json. "
        "Manifest must have metadata.rrn set.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the artifact to RRF /v2/robots/<rrn>/safety-benchmark after emit.",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Override apikey for --submit."),
) -> None:
    """Emit rcan-safety-benchmark-v1 artifact (rcan-spec §23) for this robot.

    Runs four synthetic in-process benchmarks against robot-md's own safety
    paths (estop, bounds_check, confidence_gate, full_pipeline). No
    hardware, no MCP subprocess — pure Python timing, safe in CI.

    With --sign, the artifact is wrapped in a v0.9.1 hybrid signature so a
    downstream verifier (e.g. RRF, rcan.dev) can confirm it came from the
    registered robot.
    """
    import json as _json

    from robot_md.benchmarks import build_artifact, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    artifact = build_artifact(path, iterations=iterations)

    from robot_md.parser import parse_file as _parse

    parsed = _parse(path)
    rrn = str((parsed.frontmatter.get("metadata") or {}).get("rrn") or "").strip()

    if sign:
        if not rrn:
            typer.secho(
                "error: --sign requires metadata.rrn in the manifest. "
                "Run `robot-md register` first.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    _maybe_submit(artifact, rrn=rrn, kind="safety-benchmark", do_submit=submit, api_key=api_key)

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


# ---------------------------------------------------------- §24 IFU emitter


@app.command("emit-ifu")
def emit_ifu(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Intended purpose. Overrides manifest metadata.description.",
    ),
    benchmark: Path | None = typer.Option(
        None,
        "--benchmark",
        help="Path to an rcan-safety-benchmark-v1 artifact (from emit-benchmarks). "
        "Embeds its overall_pass + per-path p95.",
    ),
    lifetime: str | None = typer.Option(
        None,
        "--lifetime",
        help="Expected lifetime string. Overrides manifest compliance.expected_lifetime.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the artifact here. Default: print to stdout."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign via v0.9.1 hybrid keypair. Manifest must have metadata.rrn.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the artifact to RRF /v2/robots/<rrn>/ifu after emit.",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Override apikey for --submit."),
) -> None:
    """Emit an rcan-ifu-v1 (Art. 13(3) Instructions for Use) artifact.

    Pulls provider identity, intended purpose, capabilities, oversight
    measures, known risks, expected lifetime, and maintenance requirements
    from the manifest. When --benchmark is supplied, embeds the §23
    artifact's pass/fail + per-path p95 latencies. --sign wraps the final
    JSON in the same hybrid wire format used by register and emit-benchmarks.
    """
    import json as _json

    from robot_md.ifu import build_artifact, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    artifact = build_artifact(
        path,
        description=description,
        benchmark=benchmark,
        lifetime=lifetime,
    )

    rrn = artifact["provider_identity"]["rrn"].strip()

    if sign:
        if not rrn:
            typer.secho(
                "error: --sign requires metadata.rrn in the manifest. "
                "Run `robot-md register` first.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    _maybe_submit(artifact, rrn=rrn, kind="ifu", do_submit=submit, api_key=api_key)

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


# ---------------------------------------------------------- Art. 11 summary


@app.command("emit-art11")
def emit_art11(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    sbom: Path | None = typer.Option(
        None,
        "--sbom",
        help="Path to a CycloneDX (or other) SBOM file. Referenced by path in the artifact.",
    ),
    artifacts_dir: Path | None = typer.Option(
        None,
        "--artifacts-dir",
        help="Directory containing signed §22-26 artifact JSON files. "
        "Inventoried into notified_body_submission.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the artifact here. Default: print to stdout."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign via v0.9.1 hybrid keypair. Manifest must have metadata.rrn.",
    ),
) -> None:
    """Emit a robot-md-art11-summary-v0 (EU AI Act Art. 11 technical-doc summary).

    Aggregates the eight Art. 11 categories from the manifest, the on-disk
    signed-artifacts inventory, and the per-robot post-market incident log.
    Schema is intentionally an aggregator name (not rcan-art11-v1) since
    rcan-spec hasn't defined an Art. 11 wire format upstream — this is
    a notified-body-readable dossier that points at authoritative pieces.
    """
    import json as _json

    from robot_md.art11 import build_artifact, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    artifact = build_artifact(path, sbom_path=sbom, signed_artifacts_dir=artifacts_dir)

    if sign:
        rrn = artifact["rrn"]
        if not rrn:
            typer.secho(
                "error: --sign requires metadata.rrn in the manifest. "
                "Run `robot-md register` first.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


# ---------------------------------------------------------- apikey reissue


@app.command("request-apikey")
def request_apikey(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    operation: str = typer.Option(
        "reissue",
        "--operation",
        help="'reissue' (default; replace lost apikey) or 'new' (issue an additional one).",
    ),
    reason: str | None = typer.Option(
        None, "--reason", help="Optional human-readable reason recorded in the request."
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the signed request here. Default: print to stdout.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the signed request to RRF /v2/robots/<rrn>/apikey-requests. "
        "On 2xx the issued apikey is auto-saved to ~/.robot-md/keys/<rrn>.apikey "
        "(mode 600) and the response body is printed to stdout.",
    ),
    endpoint: str = typer.Option(
        "https://robotregistryfoundation.org",
        "--endpoint",
        help="RRF base endpoint. Override for staging / self-hosted.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Build the request without signing — no keystore touched.",
    ),
) -> None:
    """Build a signed apikey-reissue request for an existing RRN.

    Usable when the operator holds the signing keypair but lost (or never
    received) the apikey for an RRN. The signature on the request body
    authenticates against the RRF-registered pq_signing_pub — no bearer
    token needed (that's the whole point — apikey is what we don't have).

    Default behaviour: emit a signed JSON document to stdout that the
    operator hands to RRF support out-of-band. With --submit, POSTs to
    the apikey-requests endpoint and auto-saves the issued apikey on
    success.
    """
    import json as _json

    from robot_md.apikey_request import (
        SubmitError,
        build_request,
        persist_response,
        sign_request,
        submit_request,
    )

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho(
            "error: manifest has no metadata.rrn. There's nothing to request "
            "an apikey for. Run `robot-md register` to mint a fresh RRN.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    try:
        artifact = build_request(rrn, operation=operation, reason=reason)
    except ValueError as e:
        typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from e

    if not dry_run:
        try:
            artifact = sign_request(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    if submit:
        if dry_run:
            typer.secho(
                "error: --submit is incompatible with --dry-run "
                "(unsigned requests cannot be submitted).",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            result = submit_request(artifact, rrn=rrn, endpoint=endpoint)
        except SubmitError as e:
            typer.secho(f"submit failed: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e
        typer.secho(
            f"submitted apikey reissue request for {rrn} (HTTP {result['status']})",
            err=True,
            fg=typer.colors.GREEN,
        )
        body_str, apikey_path = persist_response(result, rrn=rrn)
        if apikey_path is not None:
            typer.secho(
                f"  saved apikey to {apikey_path} (mode 600)",
                err=True,
                fg=typer.colors.GREEN,
            )
        if output is None:
            typer.echo(body_str)
        else:
            output.write_text(body_str)
            typer.echo(f"wrote response body to {output}", err=True)
        return

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)
        typer.secho(
            "  next: hand this signed JSON to RRF support out-of-band "
            "(email/ticket) or rerun with --submit to POST to RRF directly.",
            err=True,
            fg=typer.colors.YELLOW,
        )


# ---------------------------------------------------------- §22 FRIA


def _maybe_submit(
    artifact: dict, *, rrn: str, kind: str, do_submit: bool, api_key: str | None
) -> None:
    """Optionally POST `artifact` to the kind-specific RRF endpoint. P2 helper.

    For kind="eu-register" the URL is /v2/models/<rmn>/eu-register and rmn is
    extracted from the artifact (top-level or system.rmn — both populated by
    build_artifact). For all other kinds the URL is /v2/robots/<rrn>/<kind>.

    Audit-records every attempt (success or failure). Aborts the CLI with
    exit 3 on any submission failure so the operator knows the artifact
    was emitted but didn't reach the registry.
    """
    if not do_submit:
        return
    if not rrn:
        typer.secho(
            "error: --submit requires metadata.rrn in the manifest.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    from robot_md.submit import KIND_REGISTRY, SubmitError, submit_artifact

    rmn: str | None = None
    if kind == "eu-register":
        rmn = artifact.get("rmn") or (artifact.get("system") or {}).get("rmn") or None
        if not rmn:
            typer.secho(
                "error: --submit eu-register requires metadata.rmn in the "
                "manifest (per rcan-spec §26: rmn MUST). Register a model "
                "first via /v2/models/register and add `metadata.rmn: RMN-...` "
                "to the manifest.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)

    try:
        result = submit_artifact(artifact, rrn=rrn, kind=kind, rmn=rmn, api_key=api_key)
    except SubmitError as e:
        typer.secho(f"submit failed: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=3) from e
    spec = KIND_REGISTRY[kind]
    subject_id = rrn if spec["id"] == "rrn" else rmn
    submitted_path = spec["path"].format(id=subject_id)
    typer.secho(
        f"submitted to RRF {submitted_path} (HTTP {result['status']})",
        err=True,
        fg=typer.colors.GREEN,
    )


@app.command("emit-fria")
def emit_fria(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    deployment_context: str | None = typer.Option(
        None,
        "--deployment-context",
        help="Deployment context (e.g. 'internal-warehouse-pilot'). "
        "Overrides manifest compliance.deployment_context.",
    ),
    affected_groups: list[str] | None = typer.Option(
        None,
        "--affected-group",
        help="Group affected by the system. Repeat for multiple. "
        "Overrides manifest compliance.affected_groups.",
    ),
    known_risks: list[str] | None = typer.Option(
        None,
        "--known-risk",
        help="Known risk statement. Repeat for multiple. "
        "Overrides manifest compliance.known_risks.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the artifact here. Default: print to stdout."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign via v0.9.1 hybrid keypair. Manifest must have metadata.rrn.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the artifact to RRF /v2/robots/<rrn>/fria after emit. "
        "Records the attempt in the local hash-chained audit log.",
    ),
    api_key: str | None = typer.Option(
        None, "--api-key", help="Override apikey from ~/.robot-md/keys/<rrn>.apikey for --submit."
    ),
) -> None:
    """Emit an rcan-fria-v1 (Art. 27 Fundamental Rights Impact Assessment) artifact.

    Pulls system identity from manifest metadata + capabilities; pulls
    deployment context, affected groups, known risks, and human-oversight
    measures from the manifest's compliance and safety blocks. Mirrors the
    rcan-py 3.3.0 FriaDocument shape so the artifact is wire-compatible
    with RRF /v2/robots/<rrn>/fria submissions.
    """
    import json as _json

    from robot_md.fria import build_artifact, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    artifact = build_artifact(
        path,
        deployment_context=deployment_context,
        affected_groups=affected_groups or None,
        known_risks=known_risks or None,
    )

    rrn = artifact["system"]["rrn"]

    if sign:
        if not rrn:
            typer.secho(
                "error: --sign requires metadata.rrn in the manifest. "
                "Run `robot-md register` first.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    _maybe_submit(artifact, rrn=rrn, kind="fria", do_submit=submit, api_key=api_key)

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


# ---------------------------------------------------------- §26 EU register


@app.command("emit-eu-register")
def emit_eu_register(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    fria: Path = typer.Option(
        ...,
        "--fria",
        help="Path to a signed rcan-fria-v1 document (referenced by basename in the package).",
    ),
    opencastor_version: str | None = typer.Option(
        None,
        "--opencastor-version",
        help="Runtime version for system.opencastor_version. Optional.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the artifact here. Default: print to stdout."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign via v0.9.1 hybrid keypair. Manifest must have metadata.rrn.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the artifact to RRF /v2/models/<rmn>/eu-register after emit. "
        "Requires metadata.rmn (per rcan-spec §26).",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Override apikey for --submit."),
) -> None:
    """Emit an rcan-eu-register-v1 Art. 49 submission package.

    Requires the manifest to have metadata.rrn, compliance.annex_iii_basis,
    metadata.manufacturer, and metadata.author. --fria must point at an
    existing signed rcan-fria-v1 JSON document — the package references
    it by basename, and both files must be submitted together to the
    EU AI database.
    """
    import json as _json

    from robot_md.eu_register import EuRegisterError, build_artifact, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    try:
        artifact = build_artifact(path, fria_path=fria, opencastor_version=opencastor_version)
    except EuRegisterError as e:
        typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from e

    rrn = artifact["system"]["rrn"]

    if sign:
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    _maybe_submit(artifact, rrn=rrn, kind="eu-register", do_submit=submit, api_key=api_key)

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


# ---------------------------------------------------------- §25 incidents


incidents_app = typer.Typer(
    help="rcan-spec §25 post-market monitoring: record + report serious incidents."
)
app.add_typer(incidents_app, name="incidents")


def _rrn_from_manifest(path: Path) -> str:
    from robot_md.parser import parse_file as _parse

    parsed = _parse(path)
    rrn = str((parsed.frontmatter.get("metadata") or {}).get("rrn") or "").strip()
    return rrn


@incidents_app.command("record")
def incidents_record(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    severity: str = typer.Option(
        ...,
        "--severity",
        help="'life_health' (15-day Art. 72 deadline) or 'other' (90-day).",
    ),
    category: str = typer.Option(..., "--category", help="Short tag, e.g. motor_stall."),
    description: str = typer.Option(
        ..., "--description", help="Human-readable incident description."
    ),
    system_state: str | None = typer.Option(
        None,
        "--system-state",
        help="Optional JSON dict snapshotting relevant state (e.g. '{\"duty\":0.85}').",
    ),
) -> None:
    """Append an incident to ~/.robot-md/incidents/<rrn>.jsonl (append-only)."""
    import json as _json

    from robot_md.incidents import record

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho(
            "error: manifest has no metadata.rrn. Run `robot-md register` first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    state = None
    if system_state is not None:
        try:
            state = _json.loads(system_state)
        except _json.JSONDecodeError as e:
            typer.secho(
                f"error: --system-state must be valid JSON: {e}", err=True, fg=typer.colors.RED
            )
            raise typer.Exit(code=2) from e
        if not isinstance(state, dict):
            typer.secho(
                "error: --system-state must be a JSON object.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)

    try:
        entry = record(
            rrn,
            severity=severity,
            category=category,
            description=description,
            system_state=state,
        )
    except ValueError as e:
        typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from e

    typer.echo(_json.dumps(entry, indent=2))


@incidents_app.command("report")
def incidents_report(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the artifact here. Default: print to stdout."
    ),
    sign: bool = typer.Option(
        False,
        "--sign",
        help="Sign via v0.9.1 hybrid keypair. Manifest must have metadata.rrn.",
    ),
    submit: bool = typer.Option(
        False,
        "--submit",
        help="POST the report to RRF /v2/robots/<rrn>/incident-report after emit.",
    ),
    api_key: str | None = typer.Option(None, "--api-key", help="Override apikey for --submit."),
) -> None:
    """Emit an rcan-incidents-v1 Art. 72 report for this robot."""
    import json as _json

    from robot_md.incidents import build_report, sign_artifact

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho(
            "error: manifest has no metadata.rrn. Run `robot-md register` first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    artifact = build_report(rrn)

    if sign:
        try:
            artifact = sign_artifact(artifact, rrn=rrn)
        except RuntimeError as e:
            typer.secho(f"error: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=3) from e

    _maybe_submit(artifact, rrn=rrn, kind="incident-report", do_submit=submit, api_key=api_key)

    out = _json.dumps(artifact, indent=2)
    if output is None:
        typer.echo(out)
    else:
        output.write_text(out)
        typer.echo(f"wrote {output}", err=True)


compliance_app = typer.Typer(help="EU AI Act compliance status + bundling helpers.")
app.add_typer(compliance_app, name="compliance")


@compliance_app.command("status")
def compliance_status_cmd(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    artifacts_dir: Path | None = typer.Option(
        None,
        "--artifacts-dir",
        help="Directory of signed §22-26 artifacts. Default: <manifest>/compliance/",
    ),
    probe: bool = typer.Option(
        True,
        "--probe/--no-probe",
        help="Probe RRF for reachability + RRN record + rcan_version drift. "
        "Default on; use --no-probe for offline/CI.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit the structured status dict as JSON to stdout."
    ),
    endpoint: str = typer.Option(
        "https://robotregistryfoundation.org",
        "--endpoint",
        help="RRF base endpoint for the network probe.",
    ),
) -> None:
    """One-shot pre-flight readiness check.

    Surfaces in one place: keystore (signing key + apikey), audit chain
    integrity, incidents log summary, on-disk signed artifact inventory,
    RRF reachability + record drift, per-emit-* submission readiness, and
    a ranked blocker list. Exit 4 if blockers are present, 0 if clean.
    """
    import json as _json

    from robot_md.compliance_status import format_status_text, gather_status

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    status = gather_status(
        path,
        artifacts_dir=artifacts_dir,
        network_probe=probe,
        endpoint=endpoint,
    )

    if json_out:
        typer.echo(_json.dumps(status, indent=2))
    else:
        typer.echo(format_status_text(status))

    if status["blockers"]:
        raise typer.Exit(code=4)


audit_app = typer.Typer(
    help="Hash-chained audit log: verify integrity, list submissions and gate firings."
)
app.add_typer(audit_app, name="audit")


@audit_app.command("verify")
def audit_verify(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
) -> None:
    """Walk the per-robot audit chain at ~/.robot-md/audit/<rrn>.jsonl.

    Exits 0 with `valid` reported on success; exits 4 on chain integrity
    failure (mid-stream tamper or chain split). Truncation of trailing
    entries cannot be detected without an external witness — see audit.py.
    """
    from robot_md.audit import AuditChainError, verify_chain

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho(
            "error: manifest has no metadata.rrn.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    try:
        result = verify_chain(rrn)
    except AuditChainError as e:
        typer.secho(f"audit chain INVALID: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=4) from e
    n = result["entries"]
    plural = "ies" if n != 1 else "y"
    typer.secho(
        f"audit chain valid for {rrn} ({n} entr{plural})",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        "  note: chain integrity is verified for tamper + split. "
        "Truncation of trailing entries is undetectable without an "
        "external witness (e.g., a periodic checkpoint countersigned by RRF).",
        err=True,
        fg=typer.colors.YELLOW,
    )


@audit_app.command("list")
def audit_list(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
    limit: int = typer.Option(20, "--limit", help="Max entries to show. Default 20."),
) -> None:
    """List audit log entries for this robot, oldest first."""
    from robot_md.audit import load_entries

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho("error: manifest has no metadata.rrn.", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    entries = load_entries(rrn)
    if not entries:
        typer.echo(f"no audit entries for {rrn}")
        return
    typer.echo(f"{len(entries)} audit entr{'ies' if len(entries) != 1 else 'y'} for {rrn}:")
    for e in entries[-limit:]:
        details = e.get("details") or {}
        kind = details.get("kind", "")
        status = details.get("status", "")
        outcome = details.get("outcome", "")
        typer.echo(
            f"  {e['timestamp']}  {e['event']:<20}  {kind:<18}  status={status} outcome={outcome}"
        )


@incidents_app.command("list")
def incidents_list(
    path: Path = typer.Argument(..., help="Path to a ROBOT.md file."),
) -> None:
    """List incidents from the per-robot log, newest first.

    Convenience for operators inspecting ~/.robot-md/incidents/<rrn>.jsonl.
    """
    from robot_md.incidents import load

    if not path.exists():
        typer.secho(f"error: {path} does not exist", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    rrn = _rrn_from_manifest(path)
    if not rrn:
        typer.secho(
            "error: manifest has no metadata.rrn. Run `robot-md register` first.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    entries = load(rrn)
    if not entries:
        typer.echo(f"no incidents recorded for {rrn}")
        return
    typer.echo(f"{len(entries)} incident(s) for {rrn} (newest first):")
    for e in entries:
        typer.echo(
            f"  {e['timestamp']}  {e['severity']:>11}  {e['category']:<24}  {e['description']}"
        )


@app.command()
def unregister(
    rrn: str = typer.Argument(..., help="The RRN to delete (e.g. RRN-000000000042)."),
    endpoint: str = typer.Option(
        "https://robotregistryfoundation.org/v2/robots/register",
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
    `robotregistryfoundation.org/v2/robots/<rrn>`. The local key file is
    removed after a successful delete. Does NOT modify any local ROBOT.md
    files — if you want to un-publish + clean the manifest, edit
    metadata.rrn to empty string after this returns.

    Examples:

      robot-md unregister RRN-000000000042
      robot-md unregister RRN-000000000042 --api-key "$(cat old.apikey)"
    """
    from robot_md.register import cli_unregister

    rc = cli_unregister(rrn, endpoint=endpoint, api_key=api_key)
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command(name="rotate-key")
def rotate_key(
    rrn: str = typer.Argument(..., help="RRN whose key you want to rotate."),
    endpoint: str = typer.Option(
        "https://robotregistryfoundation.org/v2/robots",
        "--endpoint",
        help="RRF base URL. Override for staging / self-hosted.",
    ),
) -> None:
    """Rotate a robot's signing key.

    Generates a new keypair locally, co-signs the rotation with old+new keys,
    and POSTs to RRF. On success, archives the old keypair for recovery.
    The archive can be used to revoke the old key if the new key is lost.
    """
    from robot_md.rotate_key import cli_rotate_key

    rc = cli_rotate_key(rrn, endpoint=endpoint)
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command(name="revoke-key")
def revoke_key(
    rrn: str = typer.Argument(..., help="RRN to revoke, e.g. RRN-000000000042."),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Optional human-readable reason recorded in the revocation entry.",
    ),
    endpoint: str = typer.Option(
        "https://robotregistryfoundation.org/v2/robots",
        "--endpoint",
        help="RRF base URL. Override for staging / self-hosted.",
    ),
) -> None:
    """Revoke a robot's signing key.

    After revocation, all §22-26 compliance intakes for this RRN will be
    refused with 403. This is a ONE-WAY operation.
    """
    from robot_md.revoke_key import cli_revoke_key

    rc = cli_revoke_key(rrn, endpoint=endpoint, reason=reason)
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command(name="verify-tier")
def verify_tier(
    rrn: str = typer.Argument(..., help="RRN to promote."),
    target: str = typer.Option(
        ..., "--target", help="Target tier: manufacturer_claimed or manufacturer_verified."
    ),
    dns_domain: str = typer.Option(
        ..., "--dns-domain", help="Domain whose _rcan-verify TXT record proves ownership."
    ),
    ruri: str | None = typer.Option(
        None, "--ruri", help="Robot's RURI base URL (required for manufacturer_verified)."
    ),
    attestation_file: Path | None = typer.Option(
        None,
        "--attestation-file",
        help="Path to a signed attestation JSON (required for manufacturer_verified).",
    ),
    endpoint: str = typer.Option("https://robotregistryfoundation.org/v2/robots", "--endpoint"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the pre-flight confirmation prompt."),
) -> None:
    """Promote a robot's verification_status.

    manufacturer_claimed requires server-side DNS TXT verification;
    manufacturer_verified also requires a signed attestation and a reachable
    RURI /.well-known/rcan-manifest.json.
    """
    from robot_md.verify_tier import cli_verify_tier

    rc = cli_verify_tier(
        rrn,
        target=target,
        dns_domain=dns_domain,
        ruri=ruri,
        attestation_file=attestation_file,
        endpoint=endpoint,
        non_interactive=yes,
    )
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
    package: str | None = typer.Argument(
        None,
        help="Optional package name. When supplied, installs every skill "
        "in <package>/skills/*.SKILL.md. Defaults to bundled using-robot-md.",
    ),
    dest: Path | None = typer.Option(
        None,
        "--dest",
        help="Skills directory (default: ~/.claude/skills).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite an existing using-robot-md/SKILL.md (no-arg flow only).",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print the bundled skill to stdout (no-arg flow only).",
    ),
    list_skills: bool = typer.Option(
        False,
        "--list",
        help="List all installed skills across packages and exit.",
    ),
) -> None:
    """Install Claude Code skills from a pip-installed package, or list available skills.

    \b
      robot-md install-skill                       # bundled using-robot-md
      robot-md install-skill log-only-actuator     # third-party package skills
      robot-md install-skill --list                # enumerate all installed skills
      robot-md install-skill --dest ./skills       # project-local skills dir
      robot-md install-skill --force               # overwrite existing (no-arg flow)
      robot-md install-skill --stdout | less       # preview bundled skill

    OQ-A resolution: REPLACE-on-conflict for `<package>` flow (single file
    per skill name).
    """
    from robot_md.skill import (
        default_skills_dir,
        install,
        install_package_skills,
        iter_all_installed_skills,
        skill_content,
    )

    if list_skills:
        for pkg, path in iter_all_installed_skills():
            out_console.print(f"{pkg}\t{path.name}")
        return

    dest_root = dest or default_skills_dir()

    if package is None:
        # Backward-compatible bundled-skill flow.
        try:
            content = skill_content()
        except FileNotFoundError as e:
            err_console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(code=FILE_ERROR) from None
        if stdout:
            sys.stdout.write(content)
            return
        try:
            written = install(dest_root, force=force)
        except FileExistsError as e:
            err_console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(code=FILE_ERROR) from None
        out_console.print(f"[green]✓[/green] installed {written}")
        out_console.print(
            "  Claude Code (with superpowers or any skill-aware harness) will "
            "auto-invoke this skill when the operator mentions the robot."
        )
        return

    # Package-name flow.
    try:
        written = install_package_skills(package, dest_root)
    except ModuleNotFoundError:
        err_console.print(
            f"[red]✗[/red] package {package!r} not installed — `pip install {package}` first"
        )
        raise typer.Exit(code=FILE_ERROR) from None
    if not written:
        err_console.print(
            f"[yellow]![/yellow] package {package!r} ships no skills "
            f"(no <package>/skills/*.SKILL.md found)"
        )
        return
    for p in written:
        out_console.print(f"[green]✓[/green] installed {p}")


@app.command()
def invoke(
    manifest: Path = typer.Argument(..., help="Path to ROBOT.md being actuated against."),
    tool: str = typer.Option(..., "--tool", help="Tool name to invoke (e.g. 'home_pose')."),
    args: str = typer.Option(
        "{}",
        "--args",
        help="Tool args as JSON object string (default: '{}').",
    ),
    gateway: str = typer.Option(
        "http://127.0.0.1:8080",
        "--gateway",
        help="Gateway base URL (e.g. 'http://127.0.0.1:8080').",
    ),
    bearer: str | None = typer.Option(
        None,
        "--bearer",
        help="Bearer token directly (mutually exclusive with --bearer-from-bearers).",
    ),
    bearer_from_bearers: Path | None = typer.Option(
        None,
        "--bearer-from-bearers",
        help="Read bearer for tier 'actuate' from a bearers.yaml file.",
    ),
    scope: str = typer.Option("actuate", "--scope", help="Envelope scope (default 'actuate')."),
    sign: bool = typer.Option(
        True,
        "--sign/--no-sign",
        help="Sign the envelope with ~/.robot-md/keys/<rrn>.signing.json (default: sign).",
    ),
    kid: str | None = typer.Option(
        None,
        "--kid",
        help="Override envelope signing kid (defaults to keypair's pq_kid).",
    ),
    print_bundle_entry: bool = typer.Option(
        False,
        "--print-bundle-entry",
        help="After a successful invoke, GET /v1/audit/last and print the entry.",
    ),
) -> None:
    """Send a real signed RCAN INVOKE envelope to a robot-md-gateway.

    Operators use this for production dispatches; cookbook readers use it as
    the actuation step. Loads the operator's signing keypair from
    ~/.robot-md/keys/<rrn>.signing.json (see `robot-md register`).

    Examples:

    \b
      robot-md invoke ROBOT.md --tool home_pose
      robot-md invoke ROBOT.md --tool grasp --args '{"target":"red_brick"}'
      robot-md invoke ROBOT.md --tool home_pose \\
          --gateway http://127.0.0.1:8080 \\
          --bearer-from-bearers ./bearers.yaml \\
          --print-bundle-entry
    """
    import json as _json

    from robot_md.invoke import (
        build_envelope,
        fetch_last_audit_entry,
        invoke_envelope,
        load_bearer_for_tier,
        sign_envelope,
    )
    from robot_md.parser import parse_file
    from robot_md.signing import load_keypair

    if bearer is None and bearer_from_bearers is None:
        err_console.print(
            "[red]✗[/red] must pass either --bearer <token> or --bearer-from-bearers <yaml>"
        )
        raise typer.Exit(code=FILE_ERROR)
    if bearer is not None and bearer_from_bearers is not None:
        err_console.print("[red]✗[/red] --bearer and --bearer-from-bearers are mutually exclusive")
        raise typer.Exit(code=FILE_ERROR)

    parsed = parse_file(manifest)
    metadata = parsed.frontmatter.get("metadata") or {}
    rrn = metadata.get("rrn")
    ruri = metadata.get("ruri")
    if not rrn or not ruri:
        err_console.print(
            f"[red]✗[/red] {manifest} must declare metadata.rrn and metadata.ruri "
            "(run `robot-md register` first)"
        )
        raise typer.Exit(code=FILE_ERROR)

    try:
        tool_args = _json.loads(args)
    except _json.JSONDecodeError as e:
        err_console.print(f"[red]✗[/red] --args must be valid JSON: {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    if not isinstance(tool_args, dict):
        err_console.print(
            f"[red]✗[/red] --args must be a JSON object, got {type(tool_args).__name__}"
        )
        raise typer.Exit(code=FILE_ERROR)

    envelope = build_envelope(
        ruri=ruri,
        tool_name=tool,
        tool_args=tool_args,
        manifest_path=str(manifest.resolve()),
        scope=scope,
    )

    if sign:
        kp = load_keypair(rrn)
        if kp is None:
            err_console.print(
                f"[red]✗[/red] no signing keypair at ~/.robot-md/keys/{rrn}.signing.json — "
                "run `robot-md register` first, or pass --no-sign"
            )
            raise typer.Exit(code=FILE_ERROR)
        envelope = sign_envelope(envelope, kp, kid=kid or kp.pq_kid)

    if bearer_from_bearers is not None:
        try:
            bearer = load_bearer_for_tier(bearer_from_bearers, "actuate")
        except (FileNotFoundError, LookupError, ValueError) as e:
            err_console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(code=FILE_ERROR) from None

    try:
        result = invoke_envelope(envelope=envelope, gateway_url=gateway, bearer=bearer)
    except RuntimeError as e:
        err_console.print(f"[red]✗[/red] invoke failed: {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    out_console.print(_json.dumps(result, indent=2))

    if print_bundle_entry:
        try:
            entry = fetch_last_audit_entry(gateway_url=gateway, bearer=bearer)
            out_console.print("[dim]--- /v1/audit/last ---[/dim]")
            out_console.print(_json.dumps(entry, indent=2))
        except RuntimeError as e:
            err_console.print(f"[yellow]![/yellow] could not fetch audit entry: {e}")


# ---------------------------------------------------------------- actuator
actuator_app = typer.Typer(
    help="Manage robot-md-gateway actuators (init in v1.6.0; search + publish coming in v1.7.0)."
)
app.add_typer(actuator_app, name="actuator")


@actuator_app.command("init")
def actuator_init_cmd(
    name: str = typer.Argument(
        ...,
        help="Package name in kebab-case (e.g. 'my-camera-stack').",
    ),
    parent: Path | None = typer.Option(
        None,
        "--parent",
        help="Directory to create the package under (default: cwd).",
    ),
    author: str = typer.Option(
        "anonymous@robot-md.local",
        "--author",
        help="Author identifier for plugin.json metadata.",
    ),
    description: str = typer.Option(
        "Production actuator for robot-md-gateway.",
        "--description",
        help="One-line description (used in pyproject + plugin.json).",
    ),
) -> None:
    """Scaffold a production actuator package.

    Produces a Python-package + Claude-plugin sibling layout:

    \b
      <name>/
      ├── pyproject.toml         # entry-point declared
      ├── src/<name>/actuator.py # Protocol skeleton (NotImplementedError)
      ├── claude-plugin/         # Anthropic plugin layout
      ├── skills/                # bundled SKILL.md
      └── tests/test_actuator.py # Protocol-conformance scaffold

    After scaffolding:

    \b
      cd <name>
      pip install -e '.[dev]'
      pytest                       # confirms Protocol conformance
      robot-md-gateway list-actuators   # confirms entry-point auto-discovery
      # Then open Claude Code and ask it to fill in execute() against your ROBOT.md.
    """
    from robot_md.actuator import scaffold_actuator_package

    if parent is None:
        parent = Path.cwd()

    try:
        out = scaffold_actuator_package(
            name,
            parent,
            author=author,
            description=description,
        )
    except FileExistsError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None
    except ValueError as e:
        err_console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(code=FILE_ERROR) from None

    out_console.print(f"[green]✓[/green] scaffolded {out}")
    out_console.print("\n  Next:")
    out_console.print(f"    cd {out.name}")
    out_console.print("    pip install -e '.[dev]'")
    out_console.print("    pytest")
    out_console.print("    robot-md-gateway list-actuators")


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
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help=(
            "Skip interactive prompts (assume yes). For --extrinsic this auto-"
            "confirms both the initial 'arm will move' prompt and the high-"
            "residual acceptance prompt. Required when invoking from a script."
        ),
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
        result = phase_calibrate_extrinsic(
            path, bus=bus, camera=cam, interactive=True, auto_yes=yes
        )
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
    manifest: Path | None = typer.Argument(
        None,
        help="Path to a ROBOT.md file. If omitted, walks up from cwd to find one.",
    ),
) -> None:
    """Start the robot-md MCP server over stdio (same as `robot-md-mcp`).

    When invoked without a manifest argument (the plugin's default),
    auto-discovers ROBOT.md by walking up from the current working directory.
    """
    import sys as _sys
    from pathlib import Path as _Path

    from robot_md.mcp.server import find_manifest_via_cwd_walk
    from robot_md.mcp.server import main as _mcp_main

    if manifest is None:
        found = find_manifest_via_cwd_walk(_Path.cwd())
        if found is None:
            print(
                f"error: no ROBOT.md found walking up from {_Path.cwd()}. "
                f"Pass a path explicitly: robot-md mcp /path/to/ROBOT.md",
                file=_sys.stderr,
            )
            raise typer.Exit(code=2)
        manifest = found

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


from robot_md.hotplug.cli import app as hotplug_daemon_app  # noqa: E402
from robot_md.hotplug.cli import operator_app as hotplug_operator_app  # noqa: E402
from robot_md.spatial_eval.cli import app as spatial_eval_app  # noqa: E402

app.add_typer(hotplug_daemon_app, name="hotplug-daemon")
app.add_typer(hotplug_operator_app, name="hotplug")
app.add_typer(spatial_eval_app, name="spatial-eval")


if __name__ == "__main__":
    app()
