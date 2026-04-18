"""`robot-md init` — zero-to-ROBOT.md in one command.

Default mode is **super-duper-quick**: no prompts. Scans hardware, matches
against a preset library, emits a validated draft. If nothing matches, falls
back to plain `autodetect`.

Interactive mode opt-in: `--wizard`.

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
    name: str                               # e.g. "so_arm101"
    match: dict[str, Any]                   # match rules (see match_score)
    data: dict[str, Any]                    # full preset body (physics, drivers, ...)

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
    """Return the highest-scoring preset, or None if all score zero and no
    empty-match fallback exists."""
    scored = [match_score(p, scan) for p in presets]
    scored.sort(key=lambda r: r.score, reverse=True)
    if not scored:
        return None
    # Always return the best (top score), even if 0 — fallback is a valid preset
    # (e.g. minimal.yaml). Caller can check `result.score == 0` to detect
    # "nothing actually matched" and respond with a TODO.
    return scored[0]


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
        "rcan_version": "3.0",
        "schema": "https://robotmd.dev/schema/v1/robot.schema.json",
        "metadata": {
            "robot_name": robot_name,
            "rrn": "",                    # empty until registered (v0.2)
            "license": "Apache-2.0",
        },
    }
    # Copy every non-match key from the preset
    for k, v in preset.data.items():
        if k == "body_hints":
            continue                       # used separately when rendering body
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

def quick(
    out_path: Path,
    *,
    robot_name: str | None = None,
    preset_name: str | None = None,
    force: bool = False,
) -> int:
    """Super-duper-quick init. Zero prompts."""
    import socket

    if out_path.exists() and not force:
        print(f"error: {out_path} already exists (pass --force to overwrite)", file=sys.stderr)
        return 2

    scan = scan_system()
    presets = load_presets()
    if not presets:
        print("error: no presets found", file=sys.stderr)
        return 2

    if preset_name:
        sel = next((p for p in presets if p.name == preset_name or p.display_name == preset_name), None)
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

    name = robot_name or f"robot-{socket.gethostname()}"
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
        f"  claude mcp add robot-md -- npx -y robot-md-mcp \"$(pwd)/{out_path.name}\"\n",
        file=sys.stderr,
    )
    return 0


def wizard(out_path: Path, *, force: bool = False) -> int:
    """Interactive 7-step walkthrough. Opt-in via `--wizard`."""
    import socket

    if out_path.exists() and not force:
        print(f"error: {out_path} already exists (pass --force to overwrite)", file=sys.stderr)
        return 2

    def ask(prompt: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        try:
            ans = input(f"{prompt}{suffix} > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\naborted.", file=sys.stderr)
            sys.exit(1)
        return ans or (default or "")

    print("robot-md init (wizard mode) — 7 steps.\n", file=sys.stderr)

    # 1. Robot name
    default_name = f"robot-{socket.gethostname()}"
    name = ask("1/7 · Robot name? (short, lowercase)", default=default_name)

    # 2. Preset
    presets = load_presets()
    preset_names = [p.display_name for p in presets]
    print(f"\n2/7 · Known preset? Options: {', '.join(preset_names)} (or 'none' for autodetect only)", file=sys.stderr)
    preset_choice = ask("    preset", default="autodetect").strip().lower()

    # 3. Scan
    print("\n3/7 · Scanning hardware...", file=sys.stderr)
    scan = scan_system()

    # 4. Pick preset
    if preset_choice in ("none", "autodetect", ""):
        chosen = pick_best(presets, scan)
        print(f"    → auto-selected preset: {chosen.preset.display_name} (score={chosen.score})", file=sys.stderr)
    else:
        sel = next((p for p in presets if p.name == preset_choice or p.display_name == preset_choice), None)
        if sel is None:
            print(f"    preset {preset_choice!r} not found; falling back to autodetect", file=sys.stderr)
            chosen = pick_best(presets, scan)
        else:
            chosen = MatchResult(preset=sel, score=100, reasons=["wizard explicit"])

    # 5. Write draft
    fm = merge_preset_into_draft(chosen.preset, name, scan)
    body_hints = chosen.preset.data.get("body_hints", {}) or {}
    text = render_draft(fm, body_hints)
    out_path.write_text(text)
    print(f"\n4/7 · wrote draft to {out_path}", file=sys.stderr)

    # 5. Calibrate --zero prompt
    do_zero = ask("\n5/7 · Run `calibrate --zero` now? (pose arm, press Enter) (y/n)", default="n").lower()
    if do_zero.startswith("y"):
        from robot_md.calibrate import cli_calibrate_zero
        cli_calibrate_zero(str(out_path))

    # 6. Sign calibration — noted as future
    print("\n6/7 · calibrate --sign (encoder sign verification) — not implemented yet (task #44)", file=sys.stderr)

    # 7. Hand-eye — noted as future
    print("7/7 · calibrate --hand-eye — not implemented yet (task #44)\n", file=sys.stderr)

    # Final hint
    print(
        "✓ Done. Try:\n"
        f"  robot-md validate {out_path}\n"
        f"  claude mcp add robot-md -- npx -y robot-md-mcp \"$(pwd)/{out_path.name}\"\n",
        file=sys.stderr,
    )
    return 0
