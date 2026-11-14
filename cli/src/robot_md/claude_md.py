"""robot-md claude-md — generate a CLAUDE.md file for a robot project.

The CLAUDE.md template teaches Claude Code (and any CLAUDE.md-aware
harness) how to recognize robot-related intent and which robot-md
verbs to dispatch. Drop it in the same directory as `ROBOT.md`.

Template is inlined in this module as `_TEMPLATE_INLINE` — bundled
with the wheel, no external files required.
"""
# ruff: noqa: E501  # long lines are intentional in the embedded markdown template

from __future__ import annotations

from datetime import date
from pathlib import Path

from robot_md import motion_gates
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
| "Something's wrong" / "It's not responding" / "Why is X broken" | Run `robot-md doctor --path ROBOT.md --hardware off`. Report each non-pass check. Keep `--hardware off`: without it, doctor opens the servo port and reads every servo when one is plugged in. A hardware check (`--hardware on`) is the person's to run. |
| "Is the manifest valid?" / "Did I break something?" | Run `robot-md validate ROBOT.md`. |
| "Pose the arm at zero" / "Calibrate" | Give the person `robot-md calibrate --zero ROBOT.md` to run at the machine. Calibration opens the servo port directly (and `--extrinsic` moves the arm), so you don't run it. |
| "Teach a pose" / "record this position" | Give the person `robot-md pose teach` to run at the machine. It opens the servo port and releases torque, so the arm goes limp. |
| "Publish my robot" / "Give it a public URL" | `robot-md publish-discovery ROBOT.md --url <URL>` writes `.well-known/robot-md.json`. |
| "Pick up the X" / any physical motion | {{MOTION_ROW}} |

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

MCP tools (also available): `validate`, `render`, `estop` (sends robot-md-gateway's stop), `estop_clear` (always refused: the person clears a stop with their own commission-tier credential, then reconnects the MCP server, which releases its own latch), `execute_capability` and `execute_task` (sent to robot-md-gateway; `status: ok` means the gateway ran the call, so check `reached` before treating a move as done).

## Safety posture

**Motion goes only through robot-md-gateway, and only with a person at the machine.** Read `ROBOT.md:safety` before the first motion. Before any motion, the person confirms they are at the machine, watching, with a hand on a hardware stop that does not depend on software; the `estop` tool is a software stop and is not that. A reply in chat is never authorization for motion: the gateway decides. A gate that needs a person (`require_auth: true`, or not set) needs their confirmation from outside this conversation, robot-md has no path for one yet, and such a gate covers every motion, so robot-md's MCP server refuses every motion while one stands. Never drive the gateway yourself (`robot-md invoke`, `curl`, a script): that goes around this server's stop latch and gate checks. Never clear a stop yourself, never write to the servo port or run a command that opens it, and never start a test run (Bounded Embodiment EV runs, `robot-md trial`): the person does. If the bounded-embodiment plugin is in your session, its rule applies too, and the stricter rule wins: it has you call no motion tool on real hardware at all.

Declared gates for this robot:

{{HITL_GATES_LIST}}

{{MOTION_GATE_SUMMARY}}

## What this robot is running on

- Primary driver: {{DRIVER}}
- Registered RRN: {{RRN}}{{PUBLIC_RESOLVER_LINE}}

## Conventions for this project

- **Do not** edit `ROBOT.md` fields under `metadata.*` without asking — those are bound to the registry entry and changing them creates drift.
- **Do not** commit `~/.robot-md/keys/*` — API keys live outside the project.
- When adding a new capability, also update the prose body's "What this robot can do" section so the description and the declaration stay aligned.

## Escalation

If no gate is declared and the motion could cause harm (grasping unknown objects, high velocity, near the workspace boundary), **surface the gap to the operator**. Don't silently proceed; don't silently decline. Say: "Your manifest doesn't declare a gate for this scope. Adding one to ROBOT.md is your decision." Adding a gate that needs a person stops all MCP motion until robot-md can take that person's confirmation from outside the chat; never ask for it in chat.

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

    gates = [g for g in (safety.get("hitl_gates") or []) if isinstance(g, dict)]
    if gates:
        lines = []
        for g in gates:
            scope = g.get("scope", "?")
            if motion_gates.coverage(g) == "all_motion":
                suffix = (
                    " — needs a person's confirmation from outside this chat, so "
                    "robot-md refuses every motion while it stands"
                )
            elif motion_gates.requires_person(g):
                suffix = " — needs a person's confirmation from outside this chat; covers no motion"
            else:
                suffix = " — `require_auth: false`: informational"
            lines.append(f"- `{scope}`{suffix}")
        gates_block = "\n".join(lines)
    else:
        gates_block = "*No HITL gates declared.* Flag this to the operator."

    covering = motion_gates.gates_covering_motion(gates)
    if covering:
        scopes = [f"`{g.get('scope')}`" for g in covering]
        names = scopes[0] if len(scopes) == 1 else ", ".join(scopes[:-1]) + " and " + scopes[-1]
        motion_summary = (
            "**On this robot, robot-md's MCP server refuses every motion.** "
            f"{names} {'needs' if len(covering) == 1 else 'need'} a person's confirmation "
            "from outside this conversation, robot-md has no path for one yet, and a gate "
            "that needs one covers every motion. `execute_capability` and `execute_task` "
            "answer `hitl_gate`; reads such as `status.report` still work. Tell the person, "
            "and don't look for another route to move the robot."
        )
        motion_row = (
            "robot-md's MCP server refuses every motion on this robot (see Safety posture): "
            "tell the person, and hand them the steps if they want to run them at the "
            "machine. Don't look for another route."
        )
    else:
        motion_summary = (
            "No declared gate needs a person, so robot-md-gateway decides every motion."
        )
        motion_row = (
            "If the bounded-embodiment plugin is in your session, hand the steps to the "
            "person. Otherwise call `mcp__robot-md-{{ROBOT_NAME}}__execute_capability`, "
            "which sends the capability to robot-md-gateway; the gateway decides and "
            "enforces the limits. Only with the person at the machine and a hand on a "
            'hardware stop. A chat "yes" is not authorization. Report the gateway\'s '
            "answer as given, including `reached`."
        )

    if drivers:
        primary = drivers[0]
        driver_line = (
            f"{primary.get('protocol', '?')} @ {primary.get('port') or primary.get('host') or '?'}"
        )
    else:
        driver_line = "(none declared)"

    text = _load_template()
    text = text.replace("{{MOTION_ROW}}", motion_row)
    text = text.replace("{{MOTION_GATE_SUMMARY}}", motion_summary)
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
