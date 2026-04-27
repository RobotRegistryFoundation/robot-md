"""`robot-md init` — zero-to-actuatable ROBOT.md in one command.

Default flow (`default_flow`) walks five phases: write manifest → register
(opt-in) → install skill → sign calibration → zero
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

import contextlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from robot_md.autodetect import scan_system

PRESETS_DIR = Path(__file__).parent / "presets"

# Capability prefixes that require the hardware runtime (i.e., a backend
# that can drive hardware or read sensors). Used by
# `_emit_motion_extras_hint` to decide whether to print the
# `pip install 'robot-md[hardware]'` reminder.
# Keep this in sync with skills/using-robot-md SKILL.md
# 'Motion intent without motion tools' stanza.
_HARDWARE_RUNTIME_CAPABILITY_PREFIXES = ("arm.", "nav.", "gripper.", "perceive.")


def _emit_motion_extras_hint(capabilities: list[str]) -> None:
    """If manifest declares hardware-relevant capabilities, print the install hint.

    No-op when capabilities is empty or only contains non-hardware entries
    (e.g., compute.train, logging.publish on a sensor-aggregation robot).
    Per SP1 §2.2 + revisions R1+R3.
    """
    import sys

    if not capabilities:
        return
    has_motion = any(
        any(cap.startswith(prefix) for prefix in _HARDWARE_RUNTIME_CAPABILITY_PREFIXES)
        for cap in capabilities
    )
    if not has_motion:
        return
    print(
        "\nHardware runtime capabilities declared. To enable runtime control:\n"
        "  pip install 'robot-md[hardware]'\n"
        "Then in Claude Code: /mcp → arrow to `robot-md` → Reconnect.",
        file=sys.stderr,
    )


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
      +5  if any device label contains `(N servos)` matching `match.drivers.count`
      -5  per `match.negative_hints` word found in any device label
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

    # Driver servo-count match (+5 when preset declares count matching a scan device)
    if "drivers" in m and isinstance(m["drivers"], dict):
        want_count = m["drivers"].get("count")
        if want_count is not None:
            import re

            want_count = int(want_count)
            for d in devices:
                label = getattr(d, "label", "") or ""
                # Scan labels embed the count as "(N servos)"; extract.
                mo = re.search(r"\((\d+)\s+servos?\)", label)
                if mo and int(mo.group(1)) == want_count:
                    score += 5
                    reasons.append(f"servo count={want_count}")
                    break

    # Negative hints — each hit in any device label subtracts 5.
    for hint in m.get("negative_hints", []) or []:
        for d in devices:
            label = (getattr(d, "label", "") or "").lower()
            if hint.lower() in label:
                score -= 5
                reasons.append(f"negative hint {hint!r}")
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
    # Tiebreak deterministically by preset name — keeps pick_best
    # reproducible when two presets genuinely score the same on a given
    # rig (the canonical case: so_arm101 vs so_arm101_leader on a
    # follower bench where neither `negative_hints` nor `name_hints`
    # fires because the label/hostname lacks "leader").
    top.sort(key=lambda r: r.preset.name)
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
        # RRF binding. The mint/resolve/FRIA registry service is served from
        # robotregistryfoundation.org under `/v2/robots`. The public resolver
        # for human-facing URLs is at rcan.dev/r/<rrn>; it's derived from the
        # RRN at discovery time and doesn't need to be in the manifest.
        "network": {
            "rrf_endpoint": "https://robotregistryfoundation.org",
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

    _ensure_first_motion_defaults(fm)
    return fm


# --- first-motion defaults --------------------------------------------------
#
# Scaffold the manifest fields that make a robot "first-motion ready" so an
# operator running `robot-md init <preset>` doesn't discover blockers at first
# motion. Mirrors the pre-flight checks in compliance_status.
# _check_first_motion_readiness — what's checked there is what's defaulted here.
#
# Intentionally additive: if the preset declares a value, the default is NOT
# applied. Operator-supplied values always win.

_FIRST_MOTION_NAMESPACES_OBSERVATION = ("perceive", "perception", "status", "report", "observe")
_FIRST_MOTION_ACTUATION_PROTOCOLS = ("feetech_scs", "feetech", "dynamixel", "ros2_control")
_FIRST_MOTION_VISION_PROTOCOLS = ("oak_d_lr", "depthai", "realsense", "luxonis")
_FIRST_MOTION_PICK_CAPABILITIES = ("manipulate.pick", "arm.pick", "nav.pick")
_FIRST_MOTION_DEFAULT_VELOCITY_DPS = 30  # Conservative collaborative-arm budget


def _ensure_first_motion_defaults(fm: dict[str, Any]) -> None:
    """Fill in safety.hitl_gates, safety.max_joint_velocity_dps, and
    vision.object_descriptors when the manifest's capabilities + drivers
    imply they're needed and the operator/preset hasn't supplied them.
    Mutates `fm` in place. Pure additive — never overrides existing values.
    """
    capabilities = fm.get("capabilities") or []
    if not isinstance(capabilities, list):
        return
    drivers = fm.get("drivers") or []
    if not isinstance(drivers, list):
        drivers = []

    safety = fm.setdefault("safety", {})

    # 1. Default hitl_gates from declared motion namespaces.
    motion_namespaces: list[str] = []
    seen: set[str] = set()
    for cap in capabilities:
        if not isinstance(cap, str) or "." not in cap:
            continue
        ns = cap.split(".", 1)[0]
        if ns in _FIRST_MOTION_NAMESPACES_OBSERVATION or ns in seen:
            continue
        motion_namespaces.append(ns)
        seen.add(ns)
    if motion_namespaces and not safety.get("hitl_gates"):
        safety["hitl_gates"] = [{"scope": ns, "require_auth": True} for ns in motion_namespaces]

    # 2. Default max_joint_velocity_dps when any actuation driver is declared.
    has_actuation = any(
        isinstance(d, dict) and d.get("protocol") in _FIRST_MOTION_ACTUATION_PROTOCOLS
        for d in drivers
    )
    if has_actuation and "max_joint_velocity_dps" not in safety:
        safety["max_joint_velocity_dps"] = _FIRST_MOTION_DEFAULT_VELOCITY_DPS

    # 3. Default vision.object_descriptors placeholders when any *.pick
    #    capability is declared. Two canonical placeholders (red_lego,
    #    white_bowl) — enough that vision.find has SOME shape to resolve;
    #    operator replaces with real targets.
    has_pick = any(c in _FIRST_MOTION_PICK_CAPABILITIES for c in capabilities)
    if has_pick:
        vision = fm.setdefault("vision", {})
        descriptors = vision.setdefault("object_descriptors", [])
        if not descriptors:
            # Match the keys read by detectors/hsv.py: `h_ranges` (list of
            # [lo, hi] pairs), `s_min`/`s_max`/`v_min`/`v_max`. Wrong keys
            # silently fall back to "match every saturated pixel" — the
            # centroid lands at image center and dispatch resolves to
            # whatever pixel happens to sit behind that.
            descriptors.extend(
                [
                    {
                        "id": "red_lego",
                        "detector": "hsv",
                        # Red wraps both ends of the HSV hue circle.
                        "params": {
                            "h_ranges": [[0, 10], [170, 180]],
                            "s_min": 120,
                            "s_max": 255,
                            "v_min": 80,
                            "v_max": 255,
                            "min_area": 200,
                        },
                    },
                    {
                        "id": "white_bowl",
                        "detector": "hsv",
                        "params": {
                            "h_ranges": [[0, 180]],
                            "s_min": 0,
                            "s_max": 60,
                            "v_min": 180,
                            "v_max": 255,
                            "min_area": 1000,
                        },
                    },
                ]
            )


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

    try:
        from robot_md.parser import parse_file
        _parsed = parse_file(out_path)
        _capabilities = _parsed.frontmatter.get("capabilities") or []
        if isinstance(_capabilities, list):
            _emit_motion_extras_hint(_capabilities)
    except Exception:
        # Hint emission must never block init success.
        pass

    print(
        f"✓ wrote {out_path}\n"
        f"  preset: {chosen.preset.display_name}"
        + (f"  (score={chosen.score}, {', '.join(chosen.reasons)})" if chosen.reasons else "")
        + "\n"
        f"\nNext:\n"
        f"  robot-md validate {out_path}\n"
        f"  robot-md calibrate --zero {out_path}    # pose arm, record zero_pose_steps\n",
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
    "phase_auto_calibrate_ready",
    "phase_calibrate_extrinsic",
    "phase_teach_poses",
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
    do_install_mcp: bool = True,  # deprecated; ignored since 1.2.0 (SP1 R1)
    do_install_skill: bool = True,
    do_sign_cal: bool = True,
    do_zero_cal: bool = True,
    do_auto_calibrate: bool = True,
    do_teach_poses: bool = True,
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
    # install_mcp deprecated per SP1 R1 — plugin's .mcp.json handles wiring.
    phase_install_skill = _self.phase_install_skill  # type: ignore[attr-defined]
    phase_calibrate_sign = _self.phase_calibrate_sign  # type: ignore[attr-defined]
    phase_calibrate_zero = _self.phase_calibrate_zero  # type: ignore[attr-defined]
    phase_auto_calibrate_ready = _self.phase_auto_calibrate_ready  # type: ignore[attr-defined]
    phase_calibrate_extrinsic = _self.phase_calibrate_extrinsic  # type: ignore[attr-defined]
    phase_teach_poses = _self.phase_teach_poses  # type: ignore[attr-defined]

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

    # Phase 1.5: scaffold scripts/ + compliance/ alongside the manifest.
    # EU AI Act evidence has to live somewhere reproducible — emit-* artifacts
    # land in compliance/, the parameterized demo lives in scripts/. Idempotent.
    from robot_md.init_phases import phase_compliance_scaffold

    results.append(phase_compliance_scaffold(out_path))

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

    # install_mcp deprecated per SP1 R1 — plugin's .mcp.json handles wiring.

    # Phase 4: install skill
    if do_install_skill:
        results.append(phase_install_skill())

    # Phase 5: encoder-sign calibration
    if do_sign_cal:
        results.append(phase_calibrate_sign(out_path))

    # Phase 6: zero-pose calibration
    if do_zero_cal:
        results.append(phase_calibrate_zero(out_path))

    # Phase 6.5: auto-calibrate `ready` from DH params (no hardware).
    if do_auto_calibrate:
        results.append(phase_auto_calibrate_ready(manifest_path=out_path))

    # Phase 6.7: extrinsic calibration — interactive prompt; skips cleanly when
    # non-interactive, no camera, or no actuatable bus.  When running
    # interactively, attempt to open hardware so the phase can actually run.
    interactive = sys.stdin.isatty()
    bus_for_cal = None
    cam_for_cal = None
    if interactive:
        try:
            from robot_md.backends.feetech_depthai.perception import Perception
            from robot_md.backends.feetech_depthai.servo import ServoBus
            from robot_md.parser import parse_file as _parse_file
            from robot_md.robot_spec import RobotSpec

            spec = RobotSpec.from_parsed(_parse_file(out_path))
            try:
                bus_for_cal = ServoBus.from_spec(spec)
                bus_for_cal.open()
            except Exception:
                bus_for_cal = None
            try:
                cam_for_cal = Perception.from_spec(spec)
                cam_for_cal.open()
            except Exception:
                cam_for_cal = None
        except Exception:
            # Any setup failure → leave both None; phase will skip.
            bus_for_cal = None
            cam_for_cal = None

    result_cal = phase_calibrate_extrinsic(
        out_path,
        bus=bus_for_cal,
        camera=cam_for_cal,
        interactive=interactive,
    )
    results.append(result_cal)

    # Release hardware if we opened it.
    if bus_for_cal is not None:
        with contextlib.suppress(Exception):
            bus_for_cal.close()
    if cam_for_cal is not None:
        with contextlib.suppress(Exception):
            cam_for_cal.close()

    # Phase 7: teach poses (opt-in, TTY-only).
    if do_teach_poses:
        results.append(phase_teach_poses(manifest_path=out_path, interactive=sys.stdin.isatty()))

    # Phase 8: voice/audio onboarding — host-dependent (USB audio devices),
    # so placed last alongside other hardware-detection phases.
    from robot_md.init_phases import phase_voice_setup

    results.append(phase_voice_setup(out_path, non_interactive=not sys.stdin.isatty()))

    # Emit pip-install hint if the manifest's capabilities require hardware runtime.
    # Reads capabilities from the just-written manifest. Best-effort.
    try:
        from robot_md.parser import parse_file
        _parsed = parse_file(out_path)
        _capabilities = _parsed.frontmatter.get("capabilities") or []
        if isinstance(_capabilities, list):
            _emit_motion_extras_hint(_capabilities)
    except Exception:
        # Hint emission must never block init success.
        pass

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
            "(robot-md calibrate, install-skill) as needed.",
            file=sys.stderr,
        )

    if robot_name:
        print(
            f"{robot_name} is set up. Open Claude Code in this dir:\n"
            f"  cd {out_path.parent} && claude\n",
            file=sys.stderr,
        )
