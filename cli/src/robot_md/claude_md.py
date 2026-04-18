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

from robot_md.parser import parse_file

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
| "Pick up the X" / any physical motion | This is a **hardware action**. Check `safety.hitl_gates` first. If the scope matches a gate with `require_auth: true`, stop and ask for explicit approval before issuing any command. |

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

MCP tools (also available): `validate`, `render`.

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


def render_claude_md(manifest_path: Path) -> str:
    """Render a CLAUDE.md body tailored to a specific ROBOT.md.

    Reads the manifest, substitutes {{ROBOT_NAME}}, {{RRN}}, declared
    HITL gates, and driver summary into the template.
    """
    parsed = parse_file(manifest_path)
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
    return text
