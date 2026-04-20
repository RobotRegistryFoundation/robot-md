"""robot-md claude-md — generate a CLAUDE.md file for a robot project.

The CLAUDE.md template teaches Claude Code (and any CLAUDE.md-aware
harness) how to recognize robot-related intent and which robot-md
verbs to dispatch. Drop it in the same directory as `ROBOT.md`.

Template source: `integrations/claude-code/CLAUDE.md.template` in the
robot-md repo, bundled with the wheel via hatchling package_data.
"""
# ruff: noqa: E501  # long lines are intentional in the embedded markdown template

from __future__ import annotations

from datetime import date
from pathlib import Path

from robot_md.parser import ParsedRobotMd, parse_file
from robot_md.robot_spec import RobotSpec

# Template is packaged at the repo root, not inside src/. Look for it
# relative to this file's parent.parent (src/robot_md/ → src/ → repo root).
# Fall back to an inline copy if running from a wheel that didn't include it.

_TEMPLATE_INLINE = """# CLAUDE.md — {{ROBOT_NAME}}

> **Agent context file.** Drop this in the root of your robot's project (same directory as `ROBOT.md`) and Claude Code will read it at the start of every session.
>
> Template from [robot-md](https://github.com/RobotRegistryFoundation/robot-md) — customize everywhere you see `{{...}}` or `TODO`.

This project is a **robot workspace**. The file `ROBOT.md` in this directory is the authoritative declaration of what the robot is and what it can do (identity, physics, drivers, capabilities, safety gates). Consult it before answering any question about the robot.

## Recognizing robot-related intent

When the operator asks any of the following, **you should act** — not ask clarifying questions first:

| Operator intent (examples) | What to do |
|---|---|
| "What can this robot do?" / "What are its capabilities?" | Read `robot-md://{{ROBOT_NAME}}/capabilities` (MCP) or run `robot-md render ROBOT.md` and extract `capabilities[]`. |
| "What are its safety gates?" / "What's dangerous?" | Read `robot-md://{{ROBOT_NAME}}/safety` (MCP) or `robot-md render ROBOT.md` and extract `safety.hitl_gates`, `safety.estop`. |
| "Something's wrong" / "It's not responding" / "Why is X broken" | Run `robot-md doctor --path ROBOT.md`. Report each non-pass check. |
| "Is the manifest valid?" / "Did I break something?" | Run `robot-md validate ROBOT.md`. |
| "Pose the arm at zero" / "Calibrate" | `robot-md calibrate --zero ROBOT.md`. Relay the interactive prompts to the operator. |
| "Publish my robot" / "Give it a public URL" | `robot-md publish-discovery ROBOT.md --url <URL>` writes `.well-known/robot-md.json`. |
| "Pick up the X" / any physical motion | Call `mcp__robot-md-{{ROBOT_NAME}}__execute_capability` (dry-run first). Check `safety.hitl_gates` for the cap's scope; if a gate with `require_auth: true` matches, request explicit operator approval before re-running without dry-run. |

## Tooling available in this workspace

```bash
robot-md --help              # full verb list
robot-md doctor              # diagnose install + manifest + drivers
robot-md validate ROBOT.md   # schema conformance
robot-md render ROBOT.md     # frontmatter → pure YAML (for parsing)
robot-md context ROBOT.md    # Claude-ready context block (if no MCP)
robot-md publish-discovery ROBOT.md --url <url>   # emit .well-known/robot-md.json
```

If `robot-md-mcp` is registered in this session (check with `/mcp`), prefer the MCP resources over shelling out — they stay in sync with the file on disk automatically:

- `robot-md://{{ROBOT_NAME}}/frontmatter` — full parsed YAML
- `robot-md://{{ROBOT_NAME}}/capabilities` — capabilities list
- `robot-md://{{ROBOT_NAME}}/safety` — safety block
- `robot-md://{{ROBOT_NAME}}/body` — prose

MCP tools (also available): `validate`, `render`, `estop`, `estop_clear`, `execute_capability`, `execute_task`.

## Safety posture

**Never actuate the robot without consulting `ROBOT.md:safety` first.** If the operator asks for a motion that matches any `hitl_gate.scope`, pause and request explicit authorization. If the manifest declares `safety.estop.software: true`, a software e-stop is available — learn the exact driver command for it before attempting any motion.

Declared gates for this robot:

{{HITL_GATES_LIST}}

## What this robot is running on

- Primary driver: {{DRIVER}}
- Registered RRN: {{RRN}}{{PUBLIC_RESOLVER_LINE}}

## Conventions for this project

- **Do not** edit `ROBOT.md` fields under `metadata.*` without asking — those are bound to the registry entry and changing them creates drift.
- **Do not** commit `~/.robot-md/keys/*` — API keys live outside the project.
- When adding a new capability, also update the prose body's "What this robot can do" section so the description and the declaration stay aligned.

## Escalation

If the operator asks for something that *could* harm the robot, a human, or the workspace — and no matching HITL gate is declared — surface that gap explicitly. Don't silently proceed; don't silently decline. Tell the operator: "Your manifest doesn't have a gate for this scope; add one or authorize this specific action."

---

*Last updated: {{DATE}}. Keep this file short — Claude reads it every session.*
"""


def _load_template() -> str:
    """Load the template from the repo tree if present, else the inline copy."""
    # cli/src/robot_md/claude_md.py → cli/src/robot_md → cli/src → cli → repo
    here = Path(__file__).resolve()
    candidate = (
        here.parent.parent.parent.parent / "integrations" / "claude-code" / "CLAUDE.md.template"
    )
    if candidate.exists():
        return candidate.read_text()
    return _TEMPLATE_INLINE


def render_claude_md(source: Path | str | ParsedRobotMd) -> str:
    """Render a CLAUDE.md body tailored to a specific ROBOT.md.

    Accepts either a filesystem path to a ROBOT.md (str or Path) or a
    pre-parsed ``ParsedRobotMd``. Substitutes {{ROBOT_NAME}}, {{RRN}},
    declared HITL gates, and driver summary into the template, and
    splices in "Named poses" and "Known skills & blockers" sections
    whenever the spec declares any.
    """
    parsed = source if isinstance(source, ParsedRobotMd) else parse_file(source)
    fm = parsed.frontmatter or {}
    md = fm.get("metadata") or {}
    safety = fm.get("safety") or {}
    drivers = fm.get("drivers") or []

    robot_name = md.get("robot_name") or "robot"
    rrn = md.get("rrn") or "(unregistered)"
    public_resolver_line = (
        f" (resolves at `https://rcan.dev/r/{rrn}`)" if rrn and rrn != "(unregistered)" else ""
    )

    gates = safety.get("hitl_gates") or []
    if gates:
        lines = []
        for g in gates:
            scope = g.get("scope", "?")
            require = g.get("require_auth", False)
            lines.append(f"- `{scope}`{' — requires explicit authorization' if require else ''}")
        gates_block = "\n".join(lines)
    else:
        gates_block = "*No HITL gates declared.* Flag this to the operator."

    if drivers:
        primary = drivers[0]
        driver_line = (
            f"{primary.get('protocol', '?')} @ {primary.get('port') or primary.get('host') or '?'}"
        )
    else:
        driver_line = "(none declared)"

    text = _load_template()
    text = text.replace("{{ROBOT_NAME}}", robot_name)
    text = text.replace("{{RRN}}", rrn)
    text = text.replace("{{PUBLIC_RESOLVER_LINE}}", public_resolver_line)
    text = text.replace("{{HITL_GATES_LIST}}", gates_block)
    text = text.replace("{{DRIVER}}", driver_line)
    text = text.replace("{{HOSTNAME}}", md.get("device_id") or robot_name)
    text = text.replace("{{TESTS_DIR}}", "tests/")
    text = text.replace("{{DATE}}", date.today().isoformat())

    # Splice in poses + learned-skill sections derived from the typed spec.
    # These must appear AFTER the core capabilities/safety content but BEFORE
    # the trailing "Conventions" and "Escalation" sections, so agents read
    # them in the same visual band as other declared-state summaries.
    spec = RobotSpec.from_parsed(parsed)
    extra_sections = _render_pose_and_skill_sections(spec)
    if extra_sections:
        anchor = "## Conventions for this project"
        if anchor in text:
            text = text.replace(anchor, extra_sections + anchor, 1)
        else:
            # No anchor found — append before the final horizontal rule if any,
            # otherwise at the end.
            text = text.rstrip() + "\n\n" + extra_sections.rstrip() + "\n"
    return text


def _render_pose_and_skill_sections(spec: RobotSpec) -> str:
    """Build markdown for the Named-poses and Known-skills H2 sections.

    Each section is omitted entirely when its underlying collection is
    empty. Returns "" when there is nothing to surface.
    """
    chunks: list[str] = []

    poses = spec.physics.poses
    if poses:
        lines = ["## Named poses", ""]
        for name, p in poses.items():
            src = f" (source: {p.source})" if p.source else ""
            desc = f" — {p.description}" if p.description else ""
            joints_str = ", ".join(f"{k}={v}" for k, v in p.joints.items())
            suffix = f": {joints_str}" if joints_str else ""
            lines.append(f"- `{name}`{src}{desc}{suffix}")
        chunks.append("\n".join(lines))

    learned = spec.learned_skills
    if learned:
        lines = ["## Known skills & blockers", ""]
        for s in learned:
            bits = [f"**{s.id}**", f"status=`{s.status}`"]
            if s.blocked_by:
                bits.append("blocked_by=[" + ", ".join(s.blocked_by) + "]")
            if s.notes:
                bits.append(f"— {s.notes}")
            lines.append("- " + " ".join(bits))
        chunks.append("\n".join(lines))

    if not chunks:
        return ""
    return "\n\n".join(chunks) + "\n\n"


# Sentinels used to delimit our block inside an existing CLAUDE.md so re-runs
# can update in place without touching operator-authored content above/below.
BEGIN_MARKER = (
    "<!-- BEGIN robot-md — auto-generated; edit ROBOT.md then re-run "
    "`robot-md claude-md` to refresh -->"
)
END_MARKER = "<!-- END robot-md -->"


def wrap_block(rendered: str) -> str:
    """Wrap a rendered block in the robot-md sentinels for idempotent merging."""
    return f"{BEGIN_MARKER}\n{rendered.rstrip()}\n{END_MARKER}\n"


def apply_to_file(
    rendered: str,
    out_path: Path,
    *,
    force: bool = False,
) -> str:
    """Write `rendered` to `out_path`, preserving existing operator content.

    Returns a short status word: "wrote" (new file), "updated" (in-place
    replacement inside our sentinels), "appended" (sentinels added below
    existing content), or "overwrote" (--force, full replacement).
    """
    block = wrap_block(rendered)
    pre_existed = out_path.exists()

    if not pre_existed:
        out_path.write_text(block)
        return "wrote"

    if force:
        out_path.write_text(block)
        return "overwrote"

    existing = out_path.read_text()
    if BEGIN_MARKER in existing and END_MARKER in existing:
        # Replace the delimited region in place.
        import re

        pattern = re.compile(
            re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER) + r"\n?",
            re.DOTALL,
        )
        new_text = pattern.sub(block, existing, count=1)
        out_path.write_text(new_text)
        return "updated"

    # No sentinels yet — append our block below the operator's content.
    if existing.endswith("\n\n"):
        sep = ""
    elif existing.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    out_path.write_text(existing + sep + block)
    return "appended"
