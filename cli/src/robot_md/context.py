"""Emit a Claude-ready context block from a parsed ROBOT.md.

The output is designed to be fed to Claude at session start — e.g., via a
SessionStart hook in Claude Code, or as a system-level context injection.
"""

from __future__ import annotations

from robot_md.parser import ParsedRobotMd


def emit_context(parsed: ParsedRobotMd) -> str:
    """Render a parsed ROBOT.md as a single text block for planner consumption."""
    fm = parsed.frontmatter
    body = parsed.body or ""
    meta = fm.get("metadata", {})
    physics = fm.get("physics", {})
    safety = fm.get("safety", {})
    caps = fm.get("capabilities", []) or []

    lines: list[str] = []
    lines.append("# Robot context")
    lines.append("")
    lines.append(
        f"This session is operating robot **{meta.get('robot_name', '<unnamed>')}**"
        f" ({physics.get('type', '?')}, {physics.get('dof', '?')} DoF)."
    )
    if meta.get("rrn"):
        lines.append(f"RRN: `{meta['rrn']}`  RURI: `{meta.get('ruri', '—')}`")
    lines.append("")

    lines.append("## Declared capabilities")
    if caps:
        for c in caps:
            lines.append(f"- `{c}`")
    else:
        lines.append("_No capabilities declared. Robot is observational only._")
    lines.append("")

    lines.append("## Safety envelope")
    estop = safety.get("estop", {})
    lines.append(
        f"- E-stop: software={estop.get('software', False)}, "
        f"hardware={estop.get('hardware', False)}, "
        f"response_ms={estop.get('response_ms', '?')}"
    )
    if safety.get("max_joint_velocity_dps") is not None:
        lines.append(f"- Max joint velocity: {safety['max_joint_velocity_dps']} dps")
    if safety.get("payload_kg") is not None:
        lines.append(f"- Max payload: {safety['payload_kg']} kg")
    gates = safety.get("hitl_gates", [])
    if gates:
        lines.append("- Human-in-the-loop gates:")
        for g in gates:
            lines.append(
                f"  - `{g.get('scope', '?')}` (auth_required={g.get('require_auth', True)})"
            )
    lines.append("")

    lines.append("## Operator prose (from ROBOT.md body)")
    lines.append("")
    lines.append(body.strip())
    lines.append("")

    return "\n".join(lines)
