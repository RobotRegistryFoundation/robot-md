"""`robot-md init` — zero-to-actuatable ROBOT.md in one command.

Default flow (`default_flow`) walks six phases: write manifest → register
(opt-in) → install MCP → install skill → sign calibration → zero
calibration. Each phase is independently callable from `init_phases/`.
Scripted / CI callers pass `--non-interactive` to skip every phase
except manifest write (equivalent to the pre-v0.5.0 `quick`-style path).

Design principles (from spec/autodetect-prefill-roadmap.md):
  * Pre-fill is opt-in per tier; default composes all tiers.
  * Never silently guess Tier D fields; emit TODO markers instead.
  * Presets are YAML (this module) not code.
  * Autodetected fields carry provenance in comments.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from robot_md.autodetect import scan_system

PRESETS_DIR = Path(__file__).parent / "presets"


# ---------------------------------------------------------------------- loading


@dataclass
class Preset:
    """A robot preset: physics + drivers + safety + capabilities + body hints.

    Loaded from a YAML file in `cli/src/robot_md/presets/`.
    """

    name: str  # e.g. "so_arm101"
    match: dict[str, Any]  # match rules (see match_score)
    data: dict[str, Any]  # full preset body (physics, drivers, ...)

    @property
    def display_name(self) -> str:
        return self.name.replace("_", "-")


def load_presets(directory: Path | None = None) -> list[Preset]:
    """Load every *.yaml file in the presets directory."""
    directory = directory or PRESETS_DIR
    out: list[Preset] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            body = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            print(f"warning: preset {path.name} has invalid YAML: {e}", file=sys.stderr)
            continue
        if not isinstance(body, dict):
            continue
        match = body.pop("match", {}) or {}
        out.append(Preset(name=path.stem, match=match, data=body))
    return out


# --------------------------------------------------------------------- matching


@dataclass
class MatchResult:
    preset: Preset
    score: int
    reasons: list[str] = field(default_factory=list)


def match_score(preset: Preset, scan: Any) -> MatchResult:
    """Score how well a preset matches the autodetect scan.

    Uses the `autodetect.Scan` object — a flat list of :class:`Device`
    records with .protocol / .bus / .label / .path / .vid / .pid. Heuristic:

      +10 if any device matches `match.drivers.protocol`
      +5  if any PCI device's label contains a `match.pci_hints` string
      +5  if any USB device's label contains a `match.usb_hints` string
      +3  if the hostname contains a `match.name_hints` string

    The empty `match: {}` preset (e.g. `minimal.yaml`) always scores 0 —
    used as a last-resort fallback in `pick_best`.
    """
    score = 0
    reasons: list[str] = []
    m = preset.match
    devices = list(getattr(scan, "devices", []) or [])

    # Driver protocol
    if "drivers" in m and isinstance(m["drivers"], dict):
        want_proto = m["drivers"].get("protocol")
        if want_proto:
            for d in devices:
                if getattr(d, "protocol", None) == want_proto:
                    score += 10
                    reasons.append(f"driver protocol={want_proto!r}")
                    break

    # PCI hints — match against PCI devices' labels
    for hint in m.get("pci_hints", []) or []:
        for d in devices:
            if getattr(d, "bus", None) == "pci" and hint.lower() in getattr(d, "label", "").lower():
                score += 5
                reasons.append(f"pci hint {hint!r}")
                break

    # USB hints — match against USB devices' labels
    for hint in m.get("usb_hints", []) or []:
        for d in devices:
            if getattr(d, "bus", None) == "usb" and hint.lower() in getattr(d, "label", "").lower():
                score += 5
                reasons.append(f"usb hint {hint!r}")
                break

    # Name hints (match hostname)
    import socket

    host = socket.gethostname().lower()
    for hint in m.get("name_hints", []) or []:
        if hint.lower() in host:
            score += 3
            reasons.append(f"hostname hint {hint!r}")

    return MatchResult(preset=preset, score=score, reasons=reasons)


def pick_best(presets: list[Preset], scan: Any) -> MatchResult | None:
    """Return the highest-scoring preset, or None if the list is empty.

    Ties are broken in preference of an empty-match preset (e.g.
    ``minimal.yaml``) — those are purpose-built fallbacks for robots that
    don't match any specific preset. Without this, a CI machine with no
    robot hardware would get alphabetically-first ``aloha2.yaml`` just
    because every score is 0, which is worse than the intentionally
    generic fallback.
    """
    scored = [match_score(p, scan) for p in presets]
    if not scored:
        return None
    top_score = max(r.score for r in scored)
    top = [r for r in scored if r.score == top_score]
    # Among top-scored, prefer an empty-match preset (fallback-intended).
    fallback = next((r for r in top if not r.preset.match), None)
    # But only when the top score is 0 — if something actually matched
    # (even weakly), don't substitute the fallback.
    if fallback is not None and top_score == 0:
        return fallback
    return top[0]


# ----------------------------------------------------------------------- merge


def merge_preset_into_draft(
    preset: Preset,
    robot_name: str,
    scan: Any,
) -> dict[str, Any]:
    """Build a full ROBOT.md frontmatter dict from preset + operator-supplied
    name + hardware scan. Autodetect takes precedence for `drivers[].port`
    since that's machine-specific.
    """
    fm: dict[str, Any] = {
        # RCAN wire protocol. v1 spec freezes at 3.0; newer releases are
        # backward-compatible per §2.5 of rcan.dev/spec so "3.0" also covers
        # 3.1, 3.2, ... at the manifest layer.
        "rcan_version": "3.0",
        "schema": "https://robotmd.dev/schema/v1/robot.schema.json",
        "metadata": {
            "robot_name": robot_name,
            # Identity fields — `robot-md register` needs all four to mint
            # an RRN. Preset name seeds `model` with a sensible default; the
            # robot name doubles as a reasonable manufacturer + device_id
            # placeholder. Operator overrides via `init --manufacturer/--model
            # /--version-/--device-id` or by editing the manifest.
            "manufacturer": robot_name,
            "model": preset.display_name,
            "version": "1.0",
            "device_id": robot_name,
            # RRN — empty until `robot-md register` mints one against the
            # Robot Registry Foundation. Populated with the canonical
            # `RRN-NNNNNNNNNNNN` assigned at mint time; resolvable via
            # https://rcan.dev/r/<rrn>.
            "rrn": "",
            "license": "Apache-2.0",
        },
        # RRF binding. The governance home is robotregistryfoundation.org;
        # the live registry service (mint, resolve, FRIA, signed manifest)
        # runs at rcan.dev. `/r/<rrn>` returns the signed manifest,
        # `/api/v1/robots/<rrn>/fria` returns the EU AI Act FRIA reference.
        "network": {
            "rrf_endpoint": "https://rcan.dev",
            "signing_alg": "ml-dsa-65",  # RCAN 3.0 primary; ed25519 accepted at L1
            "transports": ["http"],
        },
    }
    # Copy every non-match key from the preset
    for k, v in preset.data.items():
        if k == "body_hints":
            continue  # used separately when rendering body
        fm[k] = v

    # Override driver ports with what the scan actually found
    devices = list(getattr(scan, "devices", []) or [])
    if "drivers" in fm and isinstance(fm["drivers"], list):
        for drv in fm["drivers"]:
            proto = drv.get("protocol")
            # First matching device by protocol wins
            for dev in devices:
                if getattr(dev, "protocol", None) == proto and getattr(dev, "path", None):
                    drv["port"] = dev.path
                    break

    # Inject detected cameras as additional drivers[] + physics.solver.cameras[]
    detected_cams = list(getattr(scan, "cameras", []) or [])
    if detected_cams:
        fm.setdefault("drivers", [])
        solver = fm.setdefault("physics", {}).setdefault("solver", {})
        cameras_list = solver.setdefault("cameras", [])
        for cam in detected_cams:
            streams_out: dict[str, Any] = {}
            for s in cam.streams:
                entry: dict[str, Any] = {"intrinsic": s.intrinsic}
                if s.baseline_m is not None:
                    entry["baseline_m"] = s.baseline_m
                if s.derived_from:
                    entry["derived_from"] = list(s.derived_from)
                streams_out[s.name] = entry
            fm["drivers"].append(
                {
                    "id": cam.driver_id,
                    "protocol": cam.protocol,
                    "model": cam.model,
                    "streams": streams_out,
                }
            )
            primary = "rgb" if "rgb" in streams_out else next(iter(streams_out.keys()), "rgb")
            cameras_list.append(
                {
                    "driver_id": cam.driver_id,
                    "primary_stream": primary,
                    "mount": "world",
                    "extrinsic": None,
                }
            )

    return fm


def render_draft(
    frontmatter: dict[str, Any],
    body_hints: dict[str, str] | None = None,
) -> str:
    """Render frontmatter + body into a complete ROBOT.md string."""
    body_hints = body_hints or {}
    robot_name = frontmatter.get("metadata", {}).get("robot_name", "robot")
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False)

    identity = body_hints.get("identity", f"{robot_name} — autodetected by `robot-md init`.")
    capabilities = body_hints.get("capabilities", "TODO: describe what this robot can do.")
    safety = body_hints.get("safety", "TODO: describe the safety envelope.")

    body = (
        f"# {robot_name}\n\n"
        f"## Identity\n\n{identity.strip()}\n\n"
        f"## What {robot_name} Can Do\n\n{capabilities.strip()}\n\n"
        f"## Safety Gates\n\n{safety.strip()}\n"
    )
    return f"---\n{fm_yaml}---\n\n{body}"


# ---------------------------------------------------------------------- drivers


def _default_robot_name() -> str:
    """Default `robot-<hostname>`, but skip the prefix when the hostname
    already starts with "robot" (case-insensitive). Prevents awkward
    doubles like `robot-robot` on machines whose hostname is "robot".
    """
    import socket

    host = socket.gethostname()
    if host.lower().startswith("robot"):
        return host
    return f"robot-{host}"


def non_interactive(
    out_path: Path,
    *,
    robot_name: str | None = None,
    preset_name: str | None = None,
    force: bool = False,
) -> int:
    """Manifest-only init for scripted / non-interactive callers. Zero prompts."""
    if out_path.exists() and not force:
        print(f"error: {out_path} already exists (pass --force to overwrite)", file=sys.stderr)
        return 2

    scan = scan_system()
    presets = load_presets()
    if not presets:
        print("error: no presets found", file=sys.stderr)
        return 2

    if preset_name:
        sel = next(
            (p for p in presets if p.name == preset_name or p.display_name == preset_name), None
        )
        if sel is None:
            names = [p.display_name for p in presets]
            print(f"error: preset {preset_name!r} not found. Available: {names}", file=sys.stderr)
            return 2
        chosen = MatchResult(preset=sel, score=100, reasons=["explicit --preset"])
    else:
        chosen = pick_best(presets, scan)
        if chosen is None:
            print("error: preset list empty", file=sys.stderr)
            return 2

    name = robot_name or _default_robot_name()
    fm = merge_preset_into_draft(chosen.preset, name, scan)
    body_hints = chosen.preset.data.get("body_hints", {}) or {}
    text = render_draft(fm, body_hints)
    out_path.write_text(text)

    print(
        f"✓ wrote {out_path}\n"
        f"  preset: {chosen.preset.display_name}"
        + (f"  (score={chosen.score}, {', '.join(chosen.reasons)})" if chosen.reasons else "")
        + "\n"
        f"\nNext:\n"
        f"  robot-md validate {out_path}\n"
        f"  robot-md calibrate --zero {out_path}    # pose arm, record zero_pose_steps\n"
        f'  claude mcp add robot-md -- robot-md-mcp "$(pwd)/{out_path.name}"\n',
        file=sys.stderr,
    )
    return 0


def quick(
    out_path: Path,
    *,
    robot_name: str | None = None,
    preset_name: str | None = None,
    force: bool = False,
) -> int:
    """Deprecated alias for non_interactive() — kept for external callers.

    Emits a one-time note to stderr and forwards. Remove in a future release.
    """
    print(
        "note: robot_md.init.quick is deprecated; call non_interactive() instead.",
        file=sys.stderr,
    )
    return non_interactive(out_path, robot_name=robot_name, preset_name=preset_name, force=force)


# ---------------------------------------------------------------- orchestrator

_PHASE_NAMES = (
    "PhaseResult",
    "phase_write_manifest",
    "phase_register",
    "phase_install_mcp",
    "phase_install_skill",
    "phase_calibrate_sign",
    "phase_calibrate_zero",
)


def __getattr__(name: str) -> Any:
    if name in _PHASE_NAMES:
        from robot_md import init_phases as _ip

        value = getattr(_ip, name)
        globals()[name] = value  # cache so future lookups (and mock.patch) hit __dict__
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _tally_line(r: Any) -> str:
    glyph = {"ok": "✓", "skipped": "-", "failed": "✗"}[r.status]
    # Human phase name: install_mcp → install-mcp, write_manifest → manifest (friendlier)
    label_map = {
        "write_manifest": "manifest",
        "register": "register",
        "install_mcp": "install-mcp",
        "install_skill": "install-skill",
        "sign_cal": "sign-cal",
        "zero_cal": "zero-cal",
    }
    label = label_map.get(r.phase, r.phase).ljust(13)
    return f"{glyph} {label}  {r.message}"


def _refresh_claude_md(out_path: Path) -> None:
    """Invoke claude_md.apply_to_file(render_claude_md(out_path)) — best-effort."""
    try:
        from robot_md.claude_md import apply_to_file, render_claude_md

        rendered = render_claude_md(out_path)
        apply_to_file(rendered, out_path.parent / "CLAUDE.md")
    except Exception as e:
        print(f"  (CLAUDE.md not refreshed: {e})", file=sys.stderr)


def default_flow(
    out_path: Path,
    *,
    robot_name: str | None = None,
    preset_name: str | None = None,
    force: bool = False,
    do_register: bool = False,
    contact_email: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    version_: str | None = None,
    device_id: str | None = None,
    do_install_mcp: bool = True,
    do_install_skill: bool = True,
    do_sign_cal: bool = True,
    do_zero_cal: bool = True,
    do_refresh_claude_md: bool = True,
) -> int:
    """Run the six-phase init flow. Returns 0 unless manifest-write failed.

    Each step emits a single status line to stderr. A final tally block
    summarizes what ran, was skipped, or failed. Phase ordering is:
    manifest → register → install_mcp → install_skill → sign_cal → zero_cal.
    """
    # Resolve phase callables from THIS module so mock.patch replacements are honoured
    _self = sys.modules[__name__]
    phase_write_manifest = _self.phase_write_manifest  # type: ignore[attr-defined]
    phase_register = _self.phase_register  # type: ignore[attr-defined]
    phase_install_mcp = _self.phase_install_mcp  # type: ignore[attr-defined]
    phase_install_skill = _self.phase_install_skill  # type: ignore[attr-defined]
    phase_calibrate_sign = _self.phase_calibrate_sign  # type: ignore[attr-defined]
    phase_calibrate_zero = _self.phase_calibrate_zero  # type: ignore[attr-defined]

    scan = scan_system()
    results: list[Any] = []

    # Phase 1: write manifest (required). OSError / FileExistsError on truly
    # fatal conditions (disk full, permission denied) is caught at the top
    # level per the spec — we convert to a failed PhaseResult so the tally
    # still prints cleanly instead of a raw traceback.
    try:
        r_write = phase_write_manifest(
            out_path=out_path,
            robot_name=robot_name,
            preset_name=preset_name,
            scan=scan,
            force=force,
        )
    except OSError as e:
        from robot_md.init_phases import PhaseResult as _PhaseResult

        r_write = _PhaseResult(
            phase="write_manifest",
            status="failed",
            message=f"fatal I/O error: {e}",
            detail={"reason": "os_error", "error": str(e)},
        )
    results.append(r_write)
    if r_write.status != "ok":
        _print_tally(results, out_path)
        return 2  # only fatal exit path

    # Phase 2: register (opt-in). Runs BEFORE the first CLAUDE.md refresh so
    # a successful mint's RRN lands in the generated CLAUDE.md on first write.
    if do_register:
        results.append(
            phase_register(
                out_path,
                contact_email=contact_email,
                manufacturer=manufacturer,
                model=model,
                version=version_,
                device_id=device_id,
            )
        )

    # Refresh CLAUDE.md next to the new manifest. Deferred until after
    # register so the "Registered RRN" row reflects the freshly-minted value
    # (or "(unregistered)" if register was skipped/failed) — consistent with
    # what the render_claude_md template will read from the manifest.
    if do_refresh_claude_md:
        _refresh_claude_md(out_path)

    # Phase 3: install MCP with Claude Code
    if do_install_mcp:
        results.append(phase_install_mcp(out_path))

    # Phase 4: install skill
    if do_install_skill:
        results.append(phase_install_skill())

    # Phase 5: encoder-sign calibration
    if do_sign_cal:
        results.append(phase_calibrate_sign(out_path))

    # Phase 6: zero-pose calibration
    if do_zero_cal:
        results.append(phase_calibrate_zero(out_path))

    _print_tally(results, out_path)
    return 0


def _print_tally(results: list[Any], out_path: Path) -> None:
    print("", file=sys.stderr)
    for r in results:
        print(_tally_line(r), file=sys.stderr)

    any_failed = any(r.status == "failed" for r in results)
    any_skipped = any(r.status == "skipped" for r in results)

    robot_name = None
    try:
        from robot_md.parser import parse_file

        parsed = parse_file(out_path)
        robot_name = (parsed.frontmatter.get("metadata") or {}).get("robot_name")
    except Exception:
        pass

    print("", file=sys.stderr)
    if any_failed or any_skipped:
        print(
            "Some steps were skipped or failed — rerun the individual verbs "
            "(robot-md calibrate, install-skill, claude mcp add) as needed.",
            file=sys.stderr,
        )

    # When MCP install didn't run (skip flag, skipped phase, or failed),
    # print the copy-pasteable `claude mcp add` one-liner so the operator
    # can register the server by hand. Matches what the old init printed.
    mcp_ran_ok = any(r.phase == "install_mcp" and r.status == "ok" for r in results)
    if not mcp_ran_ok and robot_name:
        print(
            f"\nTo register the MCP server manually:\n"
            f'  claude mcp add robot-md-{robot_name} -- robot-md-mcp "{out_path}"',
            file=sys.stderr,
        )

    if robot_name:
        print(
            f"{robot_name} is set up. Open Claude Code in this dir:\n"
            f"  cd {out_path.parent} && claude\n",
            file=sys.stderr,
        )
