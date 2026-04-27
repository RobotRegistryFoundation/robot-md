# SP1 Implementation Plan — Wire Python MCP Server (One-Server, Python-Required)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the npm `robot-md-mcp` server in the plugin with the Python `robot-md mcp` server. Operators get one MCP server (`robot-md`) that has both manifest reads and motion (`execute_task`, `execute_capability`, `vision_find`, etc.). Plugin requires `pip install 'robot-md[hardware]'`. Init's `install_mcp` phase deprecated. Skill text gains motion-intent stanza for the lazy-discovery path.

**Architecture:** Plugin's `.mcp.json` (in `~/robot-md-mcp` repo) declares `robot-md` server as `command: "robot-md", args: ["mcp"]`. The Python `robot-md mcp` command auto-discovers `ROBOT.md` by walking up from cwd. Two repos touched: `~/robot-md-mcp` (plugin/skill) and `~/robot-md` (Python CLI). After the change, `claude plugin install robot-md` plus `pip install 'robot-md[hardware]'` is the single supported install path.

**Tech Stack:** Python 3.10+ (`robot-md` CLI, pytest, typer), TypeScript (Claude Code plugin's `.mcp.json` is plain JSON, no TS build needed), bash (sync script + CI).

**References:**
- Spec: `docs/superpowers/specs/2026-04-26-sp1-wire-python-mcp-server-design.md`
- Revisions (authoritative on conflicts): `docs/superpowers/specs/2026-04-27-sp1-5-simplification-revisions.md` (R1 + R7)
- Pre-flight already done: SKILL.md drift resolved (commit `a4ec74c` on `~/robot-md` main)

---

## File Structure

| Path | Repo | Action | Responsibility |
|---|---|---|---|
| `.mcp.json` | `~/robot-md-mcp` | Modify | Plugin's MCP server registration. Change from npm `npx -y robot-md-mcp@^0.3` to Python `robot-md mcp`. |
| `.claude-plugin/plugin.json` | `~/robot-md-mcp` | Modify | Update description to reflect Python prereq. |
| `skills/using-robot-md/SKILL.md` | `~/robot-md-mcp` | Modify | Add motion-intent stanza (lazy-discovery trigger). Canonical source per Revision 7. |
| `cli/src/robot_md/skills/using-robot-md.SKILL.md` | `~/robot-md` | Modify (via sync) | Bundled-with-package copy. Updated by `scripts/sync-skill.sh`. |
| `cli/src/robot_md/init_phases/install_mcp.py` | `~/robot-md` | Modify | Deprecate to no-op returning `PhaseResult(status="skipped", ...)`. |
| `cli/src/robot_md/init.py` | `~/robot-md` | Modify | Add `_emit_motion_extras_hint(capabilities, out)` helper called at end of init. Stop calling `phase_install_mcp` from `default_flow`. |
| `cli/tests/unit/test_install_mcp_deprecated.py` | `~/robot-md` | Create | Verifies install_mcp returns "skipped" + does NOT shell out. |
| `cli/tests/unit/test_init_motion_extras_hint.py` | `~/robot-md` | Create | Verifies hint emitted when manifest declares motion caps; suppressed otherwise. |
| `cli/tests/integration/test_init_no_claude_mcp_add.py` | `~/robot-md` | Create | Full init flow asserts `claude mcp add` not invoked. |
| `cli/tests/manual/sp1_skill_smoke.md` | `~/robot-md` | Create | 4-item manual checklist for skill text validation. |
| `cli/tests/hardware/test_sp1_demo_path.py` | `~/robot-md` | Create | `@hardware`-marked end-to-end test on bob's RPi5. |

**No new modules, no schema changes, no new CLI subcommands.** This is a wiring change.

---

## Phase 0: Pre-flight verification

### Task 0.1: Confirm prerequisites are in place

- [ ] **Step 1: Verify SKILL.md sync infrastructure exists**

Run:
```bash
ls ~/robot-md/scripts/sync-skill.sh && grep -q "skill-sync-check" ~/robot-md/.github/workflows/ci.yml && echo "✓ sync infra present"
```

Expected: `✓ sync infra present`

If missing: SKILL.md drift fix not done. Stop and run that fix first (committed at `a4ec74c` on `~/robot-md` main per the revisions doc R7).

- [ ] **Step 2: Verify `robot-md mcp` command works locally**

Run:
```bash
cd ~/bob && timeout 2s robot-md mcp 2>&1 | head -5; echo "exit:$?"
```

Expected: server starts and is killed by timeout (exit 124 or 143). Stderr should mention "loaded ROBOT.md" or similar startup line.

If `robot-md: command not found`: install the local CLI first:
```bash
pip install -e ~/robot-md/cli
```

- [ ] **Step 3: Verify both repos exist as siblings**

Run:
```bash
test -d ~/robot-md && test -d ~/robot-md-mcp && echo "✓ both repos checked out"
```

Expected: `✓ both repos checked out`

If `~/robot-md-mcp` missing:
```bash
git clone https://github.com/RobotRegistryFoundation/robot-md-mcp.git ~/robot-md-mcp
```

- [ ] **Step 4: Confirm clean working trees in both repos**

Run:
```bash
cd ~/robot-md && git status --short && echo "---" && cd ~/robot-md-mcp && git status --short
```

Expected: no output between the lines (clean). If dirty: stash or commit existing work before starting SP1.

---

## Phase 1: Update plugin's `.mcp.json` (in `~/robot-md-mcp`)

### Task 1.1: Change MCP server registration to Python command

**Files:**
- Modify: `~/robot-md-mcp/.mcp.json`

- [ ] **Step 1: Read current `.mcp.json`**

Run:
```bash
cat ~/robot-md-mcp/.mcp.json
```

Expected output:
```json
{
  "robot-md": {
    "command": "npx",
    "args": ["-y", "robot-md-mcp@^0.3"]
  }
}
```

- [ ] **Step 2: Replace with Python command**

Edit `~/robot-md-mcp/.mcp.json` to:
```json
{
  "robot-md": {
    "command": "robot-md",
    "args": ["mcp"]
  }
}
```

- [ ] **Step 3: Verify the file parses as valid JSON**

Run:
```bash
python3 -m json.tool ~/robot-md-mcp/.mcp.json
```

Expected: file echoed back with formatted output, exit 0.

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md-mcp && git add .mcp.json && git commit -m "feat(plugin): use Python robot-md mcp server (drop npm fallback)

Plugin now requires \`pip install 'robot-md[hardware]'\` from install
time. The Python server exposes the full tool surface (validate, render,
doctor_summary, execute_task, execute_capability, vision_find, estop,
…) — operators get manifest reads AND motion in one MCP server.

Per SP1 simplification revision R1: drop the additive two-server
topology in favor of one Python server. Operators on Python-less
environments use \`claude mcp add\` manually as documented opt-in path."
```

### Task 1.2: Update plugin description to reflect Python prereq

**Files:**
- Modify: `~/robot-md-mcp/.claude-plugin/plugin.json`

- [ ] **Step 1: Read current plugin.json**

Run:
```bash
cat ~/robot-md-mcp/.claude-plugin/plugin.json
```

Expected: existing object with `name`, `description`, `author`, `homepage`.

- [ ] **Step 2: Replace `description` with Python-prereq-aware text**

Use the Edit tool to change the `description` field. Old:
```json
"description": "Bundles the using-robot-md skill and auto-registers the robot-md-mcp server. Reads a project's ROBOT.md and exposes frontmatter, capabilities, safety, and body as MCP resources, plus validate and render tools. Zero-config: ROBOT.md at the workspace root is picked up automatically.",
```

New:
```json
"description": "Bundles the using-robot-md skill and registers the robot-md MCP server. Requires `pip install 'robot-md[hardware]'` (provides the Python `robot-md` CLI). Once installed, ROBOT.md at the workspace root is picked up automatically — manifest reads + motion (execute_task / execute_capability / vision_find / estop) all in one server.",
```

- [ ] **Step 3: Verify parses**

Run:
```bash
python3 -m json.tool ~/robot-md-mcp/.claude-plugin/plugin.json > /dev/null && echo "✓ valid JSON"
```

Expected: `✓ valid JSON`

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md-mcp && git add .claude-plugin/plugin.json && git commit -m "docs(plugin): update description for Python-required model

Plugin now requires the robot-md Python CLI. Description tells operators
upfront so they don't install the plugin and discover the dep mid-session."
```

---

## Phase 2: Add motion-intent stanza to canonical SKILL.md (in `~/robot-md-mcp`)

### Task 2.1: Add the stanza

**Files:**
- Modify: `~/robot-md-mcp/skills/using-robot-md/SKILL.md`

- [ ] **Step 1: Read the skill file to find insertion point**

Run:
```bash
grep -n "^## " ~/robot-md-mcp/skills/using-robot-md/SKILL.md
```

Expected output includes lines like:
```
## Overview
## When to Use This Skill
## Intent → Action Routing
## Registration (RRF + RCAN 3.0)
## Safety Protocol
## Prefer MCP over Shell
## Slash commands (MCP prompts, v0.2.1+)
## Common Mistakes
## Red Flags
## Installation
## Integration
```

The motion-intent stanza belongs **before "Safety Protocol"** so motion-intent detection happens before motion is attempted.

- [ ] **Step 2: Insert the new stanza**

Edit `~/robot-md-mcp/skills/using-robot-md/SKILL.md`. Find the line `## Safety Protocol`. Insert ABOVE it (with a blank line separator):

```markdown
## Motion intent without motion tools

If the operator requests physical motion (any of `arm.*`, `nav.*`, `gripper.*` capabilities, or English phrasing like "find / move / grasp / place / pick up / put"), AND the `execute_task` tool is NOT in your available tools, **stop before issuing any action**. Output the upgrade instructions verbatim:

> "This robot's manifest declares motion capabilities, but the runtime isn't installed in this environment. To enable motion:
>
> 1. `pip install 'robot-md[hardware]'`
> 2. (Verify with `which robot-md` first to make sure it's on your shell PATH.)
> 3. In Claude Code: `/mcp` → arrow to `robot-md` → Reconnect.
>
> Then ask me again."

Wait for the operator to confirm. Do NOT attempt manifest reads as a substitute for motion. Do NOT attempt motion via wrong tools.

**False-positive guard:** Documentation lookups ("find docs", "find the file", "find the README") are NOT motion intent — proceed normally with manifest tools.

```

- [ ] **Step 3: Verify the section is in place**

Run:
```bash
grep -n "^## " ~/robot-md-mcp/skills/using-robot-md/SKILL.md
```

Expected: `## Motion intent without motion tools` appears immediately before `## Safety Protocol`.

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md-mcp && git add skills/using-robot-md/SKILL.md && git commit -m "feat(skill): add motion-intent stanza for lazy-discovery path

When operator requests motion AND the execute_task tool is not in
Claude's tool surface (because robot-md Python CLI isn't installed),
the skill halts and emits a verbatim upgrade block: pip install +
which robot-md verification + /mcp Reconnect.

False-positive guard: documentation verbs (find docs, find the file)
are explicitly NOT motion intent.

Implements SP1 design §2.4 (motion-intent stanza)."
```

### Task 2.2: Sync the canonical to the bundled CLI copy

**Files:**
- Modify: `~/robot-md/cli/src/robot_md/skills/using-robot-md.SKILL.md` (via sync script)

- [ ] **Step 1: Run the sync script**

Run:
```bash
~/robot-md/scripts/sync-skill.sh
```

Expected output:
```
✓ SKILL.md synced from /home/craigm26/robot-md/../robot-md-mcp/skills/using-robot-md/SKILL.md
  → /home/craigm26/robot-md/cli/src/robot_md/skills/using-robot-md.SKILL.md
```

- [ ] **Step 2: Verify the two copies are identical**

Run:
```bash
diff ~/robot-md-mcp/skills/using-robot-md/SKILL.md ~/robot-md/cli/src/robot_md/skills/using-robot-md.SKILL.md && echo "✓ in sync"
```

Expected: `✓ in sync` (no diff output before).

- [ ] **Step 3: Verify the new stanza is in the bundled copy**

Run:
```bash
grep -A 1 "^## Motion intent without motion tools" ~/robot-md/cli/src/robot_md/skills/using-robot-md.SKILL.md
```

Expected: header line + first content line of the stanza.

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md && git add cli/src/robot_md/skills/using-robot-md.SKILL.md && git commit -m "chore(skill): sync motion-intent stanza from canonical (robot-md-mcp)

Mirror of robot-md-mcp's SKILL.md addition. Done via scripts/sync-skill.sh."
```

---

## Phase 3: Deprecate `install_mcp` phase (TDD)

### Task 3.1: Write the failing test

**Files:**
- Create: `~/robot-md/cli/tests/unit/test_install_mcp_deprecated.py`

- [ ] **Step 1: Look up existing test patterns**

Run:
```bash
ls ~/robot-md/cli/tests/unit/ | grep -i mcp; echo "---"; head -40 ~/robot-md/cli/tests/unit/test_install_mcp.py 2>/dev/null
```

Expected: existing `test_install_mcp.py` shows the current test pattern. We're replacing the behavior, so the existing test will fail until we update it.

- [ ] **Step 2: Create the new deprecation test**

Create `~/robot-md/cli/tests/unit/test_install_mcp_deprecated.py` with:

```python
"""install_mcp phase is deprecated to a no-op per SP1.

Per the simplified one-server design (R1), the plugin's .mcp.json wires
the Python `robot-md mcp` server. init no longer needs `claude mcp add`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.init_phases.install_mcp import phase_install_mcp


@pytest.fixture
def stub_manifest(tmp_path: Path) -> Path:
    """Minimal valid ROBOT.md so phase doesn't fail on parse."""
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "metadata:\n"
        "  robot_name: stub\n"
        "physics:\n"
        "  type: arm\n"
        "  dof: 6\n"
        "drivers: []\n"
        "capabilities: []\n"
        "---\n"
        "# stub\n"
    )
    return p


def test_phase_install_mcp_returns_skipped(stub_manifest: Path):
    """The deprecated phase must return status=skipped, never ok or failed."""
    result = phase_install_mcp(stub_manifest)
    assert result.status == "skipped"
    assert result.phase == "install_mcp"


def test_phase_install_mcp_does_not_shell_out(stub_manifest: Path):
    """The deprecated phase must NOT call subprocess (no `claude mcp add`)."""
    with patch.object(subprocess, "run") as mock_run:
        phase_install_mcp(stub_manifest)
    assert mock_run.call_count == 0, (
        f"install_mcp shelled out {mock_run.call_count} times — "
        "should be 0 in the deprecated implementation"
    )


def test_phase_install_mcp_message_explains_plugin_handles_wiring(
    stub_manifest: Path,
):
    """Message should tell operators the plugin handles MCP wiring now."""
    result = phase_install_mcp(stub_manifest)
    assert "plugin" in result.message.lower()
    assert "/mcp" in result.message or "Reconnect" in result.message


def test_phase_install_mcp_signature_unchanged_for_backward_compat(
    stub_manifest: Path,
):
    """Old callers passing command/scope kwargs must not break."""
    # Was: phase_install_mcp(path, command="robot-md-mcp", scope="local")
    result = phase_install_mcp(stub_manifest, command="robot-md-mcp", scope="local")
    assert result.status == "skipped"
```

- [ ] **Step 3: Run the test to confirm it fails**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_install_mcp_deprecated.py -v 2>&1 | tail -20
```

Expected: 4 failures, all in `test_install_mcp_deprecated.py`. Errors should reference current behavior (returns `ok` or shells out).

### Task 3.2: Implement the deprecation

**Files:**
- Modify: `~/robot-md/cli/src/robot_md/init_phases/install_mcp.py`

- [ ] **Step 1: Read the current file**

Run:
```bash
cat ~/robot-md/cli/src/robot_md/init_phases/install_mcp.py
```

Expected: current content with `parse_file`, `add` shell-out, `Scope` import.

- [ ] **Step 2: Replace the file body**

Use the Write tool to replace `~/robot-md/cli/src/robot_md/init_phases/install_mcp.py` with:

```python
"""DEPRECATED: install_mcp phase no longer wires the MCP server.

Per SP1 simplification revision R1, the `robot-md` plugin's .mcp.json
declares the Python `robot-md mcp` server directly. init no longer needs
to run `claude mcp add`. This phase is preserved as a no-op for backward
compatibility — old scripts calling `phase_install_mcp(...)` keep
working but get a clear "skipped" result.

Operators upgrade their MCP wiring via:
  1. `claude plugin install robot-md` (or `/plugin update robot-md`)
  2. `pip install 'robot-md[hardware]'`
  3. `/mcp` → Reconnect `robot-md`

For non-plugin operators, `install_mcp_claude_code.add(...)` is still
exported and can be called manually.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from robot_md.init_phases import PhaseResult

# Kept as a type alias so external callers importing Scope from this
# module continue to work after the deprecation.
Scope = Literal["local", "user", "project"]


def phase_install_mcp(
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """No-op deprecation. Returns status=skipped with explanation.

    Signature preserved for backward compat — `command` and `scope`
    args are ignored.
    """
    return PhaseResult(
        phase="install_mcp",
        status="skipped",
        message=(
            "MCP wiring is handled by the robot-md plugin's .mcp.json. "
            "After `pip install 'robot-md[hardware]'`, run `/mcp` → "
            "Reconnect `robot-md` (or restart Claude Code). "
            "No per-robot `claude mcp add` needed."
        ),
        detail={
            "deprecated_in": "1.2.0",
            "reason": "plugin_handles_mcp",
            "ignored_args": {"command": command, "scope": scope},
        },
    )
```

- [ ] **Step 3: Run the test to confirm it now passes**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_install_mcp_deprecated.py -v 2>&1 | tail -10
```

Expected: 4 passes.

- [ ] **Step 4: Run the existing test suite to check for regressions**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_install_mcp.py tests/integration/ -v 2>&1 | tail -30
```

Expected: existing `test_install_mcp.py` tests may FAIL (they verified the old shell-out behavior); integration tests should still pass. Note any failures — they're expected and will be cleaned up in Step 5.

- [ ] **Step 5: Update the old `test_install_mcp.py` to expect deprecated behavior**

Read the failing tests in `~/robot-md/cli/tests/unit/test_install_mcp.py` and update each to assert the new no-op contract. For each test:

If the test asserted `result.status == "ok"` after a successful shell-out, change to:
```python
assert result.status == "skipped"
```

If the test mocked `subprocess.run` and asserted it was called, replace with:
```python
assert mock_run.call_count == 0
```

If a test doesn't make sense in the new model (e.g., "test fails when claude binary missing"), delete it — the old behavior path doesn't exist anymore.

- [ ] **Step 6: Run the updated old test file**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_install_mcp.py -v 2>&1 | tail -15
```

Expected: all tests pass (or, for tests that no longer apply, they were removed).

- [ ] **Step 7: Commit**

Run:
```bash
cd ~/robot-md && git add cli/src/robot_md/init_phases/install_mcp.py cli/tests/unit/test_install_mcp.py cli/tests/unit/test_install_mcp_deprecated.py && git commit -m "feat(init): deprecate install_mcp phase to no-op (SP1 R1)

Plugin's .mcp.json now declares the Python robot-md mcp server, so init
no longer needs \`claude mcp add\`. phase_install_mcp returns
PhaseResult(status='skipped') with explanation. Function signature
preserved for backward compat — old scripts don't break, just become
quieter.

install_mcp_claude_code.add() still exported for manual use by
non-plugin operators."
```

---

## Phase 4: Add motion-extras hint to `init.py` (TDD)

### Task 4.1: Write the failing test

**Files:**
- Create: `~/robot-md/cli/tests/unit/test_init_motion_extras_hint.py`

- [ ] **Step 1: Find the public symbol that emits init's closing summary**

Run:
```bash
grep -n "^def\|emit\|hint\|motion_capabilities\|FIRST_MOTION" ~/robot-md/cli/src/robot_md/init.py | head -20
```

Expected: identifies a closing-summary function or section. There may already be a place where init prints final guidance after `default_flow` completes — we'll add the hint there.

- [ ] **Step 2: Create the test file**

Create `~/robot-md/cli/tests/unit/test_init_motion_extras_hint.py`:

```python
"""init prints the pip install hint when manifest declares motion caps.

Per SP1 §2.2 + revision R3, init emits a closing line pointing at
`pip install 'robot-md[hardware]'` whenever the manifest declares
arm.*/nav.*/gripper.*/perceive.* capabilities.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.init import _emit_motion_extras_hint


def _run_hint(capabilities: list[str], capsys) -> str:
    """Helper: call the hint emitter and return captured stderr."""
    _emit_motion_extras_hint(capabilities)
    captured = capsys.readouterr()
    return captured.err


def test_hint_emitted_for_arm_pick(capsys):
    out = _run_hint(["arm.pick", "arm.place"], capsys)
    assert "pip install" in out
    assert "robot-md[hardware]" in out


def test_hint_emitted_for_nav(capsys):
    out = _run_hint(["nav.go_to"], capsys)
    assert "pip install" in out


def test_hint_emitted_for_perceive(capsys):
    out = _run_hint(["perceive.rgb"], capsys)
    assert "pip install" in out


def test_hint_emitted_for_gripper(capsys):
    out = _run_hint(["gripper.open"], capsys)
    assert "pip install" in out


def test_hint_suppressed_for_empty_capabilities(capsys):
    out = _run_hint([], capsys)
    assert out == "" or "pip install" not in out


def test_hint_suppressed_for_nonmotion_capabilities(capsys):
    """Capabilities like compute.* don't need motion runtime."""
    out = _run_hint(["compute.train", "logging.publish"], capsys)
    assert "pip install" not in out


def test_hint_mentions_mcp_reconnect(capsys):
    """Operators need to know about the /mcp Reconnect step."""
    out = _run_hint(["arm.pick"], capsys)
    assert "/mcp" in out or "Reconnect" in out
```

- [ ] **Step 3: Run the test to confirm it fails**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_init_motion_extras_hint.py -v 2>&1 | tail -15
```

Expected: 7 errors, all `ImportError: cannot import name '_emit_motion_extras_hint' from 'robot_md.init'`.

### Task 4.2: Implement the hint helper

**Files:**
- Modify: `~/robot-md/cli/src/robot_md/init.py`

- [ ] **Step 1: Find the right insertion point in init.py**

Run:
```bash
grep -n "^def\|^_FIRST_MOTION\|capabilities" ~/robot-md/cli/src/robot_md/init.py | head -30
```

Expected: locates an existing module-level constants section near the top and a place suitable for adding a private helper (e.g., near other `_*` helpers).

- [ ] **Step 2: Add the helper function near the top of init.py**

Use the Edit tool. Find an existing module-level constant section (e.g., after `PRESETS_DIR = ...` near the top). Insert AFTER it:

```python
# Capability prefixes that require the motion runtime (i.e., a backend
# that can drive hardware). Used by `_emit_motion_extras_hint` to decide
# whether to print the `pip install 'robot-md[hardware]'` reminder.
# Keep this in sync with skills/using-robot-md SKILL.md motion-intent stanza.
_MOTION_CAPABILITY_PREFIXES = ("arm.", "nav.", "gripper.", "perceive.")


def _emit_motion_extras_hint(capabilities: list[str]) -> None:
    """If manifest declares motion-relevant capabilities, print the install hint.

    No-op when capabilities is empty or only contains non-motion entries
    (e.g., compute.train, logging.publish on a sensor-aggregation robot).
    Per SP1 §2.2 + revisions R1+R3.
    """
    import sys

    if not capabilities:
        return
    has_motion = any(
        any(cap.startswith(prefix) for prefix in _MOTION_CAPABILITY_PREFIXES)
        for cap in capabilities
    )
    if not has_motion:
        return
    print(
        "\nMotion capabilities declared. To enable runtime control:\n"
        "  pip install 'robot-md[hardware]'\n"
        "Then in Claude Code: /mcp → Reconnect `robot-md` "
        "(or restart Claude Code).",
        file=sys.stderr,
    )
```

- [ ] **Step 3: Run the test to confirm it passes**

Run:
```bash
cd ~/robot-md/cli && pytest tests/unit/test_init_motion_extras_hint.py -v 2>&1 | tail -15
```

Expected: 7 passes.

### Task 4.3: Wire the helper into the init flow

**Files:**
- Modify: `~/robot-md/cli/src/robot_md/init.py` (orchestrator function `default_flow`)

- [ ] **Step 1: Find where default_flow finishes and where to call the helper**

Run:
```bash
grep -n "def default_flow\|results.append(phase_install_mcp\|return results" ~/robot-md/cli/src/robot_md/init.py
```

Expected: locates `def default_flow(...)` and the line that calls `phase_install_mcp` near the end. Hint emission should happen AFTER all phases complete, just before return.

- [ ] **Step 2: Two edits — drop install_mcp call, add hint call**

Edit A (drop the install_mcp call):

Read the lines around `results.append(phase_install_mcp(out_path))` first to see the exact context. Then use the Edit tool to either delete that line OR replace it with:

```python
# install_mcp deprecated per SP1 R1 — plugin's .mcp.json handles wiring.
# Skip silently; old callers can still invoke phase_install_mcp explicitly.
```

Edit B (add the hint call before return):

Find the end of `default_flow` (just before `return results` or equivalent). Add:

```python
# Emit pip-install hint if the manifest's capabilities require motion runtime.
# Reads capabilities from the just-written manifest.
try:
    from robot_md.parser import parse_file
    parsed = parse_file(out_path)
    capabilities = (parsed.frontmatter.get("capabilities") or [])
    if isinstance(capabilities, list):
        _emit_motion_extras_hint(capabilities)
except Exception:
    # Hint emission must never block init success.
    pass
```

- [ ] **Step 3: Run init's existing integration tests to check nothing else broke**

Run:
```bash
cd ~/robot-md/cli && pytest tests/integration/ -v -k "init" 2>&1 | tail -25
```

Expected: existing init tests still pass. Some tests that asserted `phase_install_mcp` was called in `default_flow` will fail — those need updating in Task 4.4.

### Task 4.4: Update integration tests that asserted install_mcp ran

**Files:**
- Modify: existing integration tests under `~/robot-md/cli/tests/integration/` that mention `install_mcp`

- [ ] **Step 1: Find affected tests**

Run:
```bash
grep -rln "phase_install_mcp\|install_mcp" ~/robot-md/cli/tests/ | grep -v __pycache__
```

Expected: list of files. For each, read the test and update assertions:
- `assert phase_install_mcp called` → remove or change to assert NOT called.
- `assert "install_mcp" in [r.phase for r in results]` → either expect it absent or expect it with status="skipped".

- [ ] **Step 2: Run all init-related tests**

Run:
```bash
cd ~/robot-md/cli && pytest tests/ -v -k "init or install_mcp" 2>&1 | tail -25
```

Expected: all passes.

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/robot-md && git add cli/src/robot_md/init.py cli/tests/unit/test_init_motion_extras_hint.py cli/tests/integration/ && git commit -m "feat(init): emit motion-extras hint; drop install_mcp from default flow

When manifest declares arm.*/nav.*/gripper.*/perceive.* capabilities,
init prints a closing-line hint:

  Motion capabilities declared. To enable runtime control:
    pip install 'robot-md[hardware]'
  Then in Claude Code: /mcp → Reconnect \`robot-md\`

default_flow no longer calls phase_install_mcp (deprecated to no-op
in previous commit). Plugin's .mcp.json handles MCP wiring.

Per SP1 §2.2 + revisions R1 (one server) and R3 (single [hardware]
meta-extra)."
```

---

## Phase 5: Integration test — full init flow without `claude mcp add`

### Task 5.1: Write the failing integration test

**Files:**
- Create: `~/robot-md/cli/tests/integration/test_init_no_claude_mcp_add.py`

- [ ] **Step 1: Look up existing integration test patterns for stubbed CLI invocations**

Run:
```bash
grep -rln "subprocess.*claude\|monkeypatch.setenv\|stub.*claude" ~/robot-md/cli/tests/integration/ | grep -v __pycache__ | head
```

Expected: existing tests that stub external commands. Use the same fixture pattern.

- [ ] **Step 2: Create the integration test**

Create `~/robot-md/cli/tests/integration/test_init_no_claude_mcp_add.py`:

```python
"""SP1 integration: full init flow does NOT shell out to `claude mcp add`.

Verifies the deprecation chain end-to-end:
  - phase_install_mcp returns "skipped"
  - default_flow's results list either omits install_mcp entirely or
    includes it with status=skipped
  - subprocess never invokes `claude mcp add`
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.init import default_flow


def test_default_flow_does_not_shell_out_to_claude(tmp_path: Path):
    """End-to-end: default_flow with a so_arm101-shaped fingerprint must
    not call subprocess at all for `claude mcp add` purposes."""
    out_path = tmp_path / "ROBOT.md"

    with patch("subprocess.run") as mock_run:
        # default_flow signature: (out_path, *, do_register=False, ...).
        # See cli/src/robot_md/init.py for current params.
        results = default_flow(
            out_path=out_path,
            robot_name="testbot",
            preset_name="minimal",  # avoid hardware probe path
            do_register=False,
            do_install_mcp=False,  # explicit; default behavior post-SP1
            do_install_skill=False,
            do_calibrate_sign=False,
            do_calibrate_zero=False,
            non_interactive=True,
        )

        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else []
            assert not (
                isinstance(args, list)
                and len(args) >= 2
                and args[0] == "claude"
                and args[1] == "mcp"
            ), f"default_flow shelled out to `claude mcp …`: {args}"


def test_install_mcp_phase_result_is_skipped_or_absent(tmp_path: Path):
    """If install_mcp phase is invoked at all, it must return skipped."""
    out_path = tmp_path / "ROBOT.md"
    results = default_flow(
        out_path=out_path,
        robot_name="testbot",
        preset_name="minimal",
        do_register=False,
        do_install_mcp=True,  # explicitly opt-in to test deprecation behavior
        do_install_skill=False,
        do_calibrate_sign=False,
        do_calibrate_zero=False,
        non_interactive=True,
    )
    install_mcp_results = [r for r in results if r.phase == "install_mcp"]
    if install_mcp_results:
        assert install_mcp_results[0].status == "skipped"
```

> **Note for the implementer:** the exact `default_flow` parameter names depend on your repo. Run `grep -n "def default_flow" ~/robot-md/cli/src/robot_md/init.py` and adjust the kwargs to match. The test's INTENT is what matters: any path through `default_flow` must not call `subprocess` for `claude mcp …`.

- [ ] **Step 3: Run the test to confirm it passes**

Run:
```bash
cd ~/robot-md/cli && pytest tests/integration/test_init_no_claude_mcp_add.py -v 2>&1 | tail -15
```

Expected: 2 passes.

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md && git add cli/tests/integration/test_init_no_claude_mcp_add.py && git commit -m "test(init): assert default_flow never shells out to \`claude mcp add\`

Locks in SP1 R1 behavior at the integration boundary. Catches future
regressions where someone re-adds claude mcp add to a phase."
```

---

## Phase 6: Manual smoke checklist + hardware test scaffolding

### Task 6.1: Write the manual smoke checklist

**Files:**
- Create: `~/robot-md/cli/tests/manual/sp1_skill_smoke.md`

- [ ] **Step 1: Create the checklist**

Create `~/robot-md/cli/tests/manual/sp1_skill_smoke.md`:

```markdown
# SP1 Skill Smoke Checklist

Run before SP1 release to validate the motion-intent stanza behaves correctly.
The skill text is prompt-engineering; not unit-testable.

## Setup

1. Fresh test environment (e.g., a Docker container or a VM):
   - Claude Code installed.
   - `robot-md` plugin installed (`claude plugin install robot-md`).
   - **No** `pip install robot-md` yet (intentionally — we test the lazy path).
   - cwd contains a valid `ROBOT.md` with motion capabilities (use bob's or `examples/bob/ROBOT.md`).

2. Start Claude Code in that directory: `claude`.

3. Verify the plugin's `robot-md` MCP server appears in `/mcp` as `✗ failed`
   (because `robot-md` Python CLI is not on PATH).

## Smoke tests

For each test, expected behavior is described. Mark ✓/✗ during the run.

### 1. Motion intent → upgrade hint

Type to Claude: `Find a red lego and place it in the bowl.`

Expected:
- [ ] Skill activates.
- [ ] Skill detects `execute_task` tool is NOT in available tools.
- [ ] Output mentions `pip install 'robot-md[hardware]'`.
- [ ] Output mentions `/mcp` → Reconnect `robot-md`.
- [ ] Output mentions `which robot-md` verification step.
- [ ] Skill does NOT attempt motion via wrong tools.
- [ ] Skill does NOT silently fall back to manifest reads.

### 2. Documentation lookup → no false positive

Type to Claude: `Find the docs for arm.pick.`

Expected:
- [ ] Skill activates (using-robot-md skill).
- [ ] Skill does NOT print the upgrade hint.
- [ ] Skill answers from manifest tools (`render` or `frontmatter` resource).

### 3. Manifest read intent → no false positive

Type to Claude: `What can this robot do?`

Expected:
- [ ] Skill answers via `capabilities` resource.
- [ ] No upgrade hint.

### 4. Post-upgrade recovery

Now run in a separate shell:
```
pip install 'robot-md[hardware]'
```

Then in Claude Code:
- `/mcp` → arrow to `robot-md` → Reconnect.

Verify:
- [ ] `/mcp` shows `robot-md` as `✓ connected`.
- [ ] Tool list now includes `execute_task`, `execute_capability`,
      `vision_find`, `estop`, `validate`, `render`, `doctor_summary`.

Type to Claude: `Find a red lego and place it in the bowl.`

Expected:
- [ ] Skill activates.
- [ ] Skill checks safety (HiTL gate for arm scope).
- [ ] Asks operator for authorization.
- [ ] After authorization: calls `execute_task`.
- [ ] Robot moves (verify physically).

## If any test fails

File an issue against the spec at:
`docs/superpowers/specs/2026-04-26-sp1-wire-python-mcp-server-design.md`
with the failing test number, observed behavior, and screenshots/transcript.
```

- [ ] **Step 2: Commit**

Run:
```bash
cd ~/robot-md && git add cli/tests/manual/sp1_skill_smoke.md && git commit -m "test(sp1): add manual skill smoke checklist (4 scenarios)

Manual validation for the motion-intent stanza. Run pre-release."
```

### Task 6.2: Hardware test scaffolding

**Files:**
- Create: `~/robot-md/cli/tests/hardware/test_sp1_demo_path.py`

- [ ] **Step 1: Look up existing @hardware-marked test pattern**

Run:
```bash
ls ~/robot-md/cli/tests/hardware/ 2>/dev/null && head -30 ~/robot-md/cli/tests/hardware/test_pick_red_lego_post_calibrate.py 2>/dev/null
```

Expected: existing hardware test fixture pattern (uses `@pytest.mark.hardware`, depends on `/dev/ttyACM0` etc.).

- [ ] **Step 2: Create the SP1 hardware test stub**

Create `~/robot-md/cli/tests/hardware/test_sp1_demo_path.py`:

```python
"""SP1 hardware tests — front-loaded + lazy demo paths against bob's RPi5.

Marked @hardware so they're skipped in CI. Run only on bob:
  pytest tests/hardware/test_sp1_demo_path.py --run-hardware -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.hardware


@pytest.mark.skipif(
    not Path("/dev/ttyACM0").exists(),
    reason="bob's feetech bus not present at /dev/ttyACM0",
)
def test_sp1_path_1_python_mcp_server_starts_and_lists_tools():
    """The robot-md mcp command starts and exposes execute_task in its
    tool list when given bob's ROBOT.md via cwd-walk."""
    bob_dir = Path.home() / "bob"
    if not (bob_dir / "ROBOT.md").exists():
        pytest.skip("bob's ROBOT.md not at ~/bob/")

    # Spawn `robot-md mcp` and read the MCP handshake to confirm
    # tool list. Use the MCP Python client SDK (pre-installed via
    # `pip install -e ~/robot-md/cli`).
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command="robot-md",
        args=["mcp"],
        cwd=str(bob_dir),
    )

    import asyncio

    async def _check_tools():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                # Must include the SP1-promised motion tools.
                assert "execute_task" in tool_names
                assert "execute_capability" in tool_names
                assert "vision_find" in tool_names
                # Plus the existing manifest tools.
                assert "validate" in tool_names

    asyncio.run(_check_tools())


@pytest.mark.skipif(
    not shutil.which("robot-md"),
    reason="robot-md CLI not on PATH (front-loaded path simulates Python pre-installed)",
)
def test_sp1_path_2_lazy_recovery_simulated():
    """Simulates the lazy-discovery path: no Python CLI initially, then
    pip install + reconnect. We can't fully simulate /mcp Reconnect from
    pytest, so this test verifies the deterministic part: a fresh
    `robot-md mcp` invocation succeeds after install."""
    # The Python CLI is on PATH. Start a fresh server, confirm tools.
    # If this passes, the lazy path's "after pip install" step works.
    bob_dir = Path.home() / "bob"
    if not (bob_dir / "ROBOT.md").exists():
        pytest.skip("bob's ROBOT.md not at ~/bob/")

    result = subprocess.run(
        ["robot-md", "mcp", str(bob_dir / "ROBOT.md")],
        capture_output=True,
        timeout=2,  # killed by timeout — we just want to see it starts
    )
    # Either timed out (started successfully) or exited cleanly.
    # Failure is exit code that indicates startup error (1 with traceback
    # in stderr).
    if result.returncode not in (0, 124, -15, -9):
        pytest.fail(
            f"robot-md mcp failed to start: exit={result.returncode}, "
            f"stderr={result.stderr.decode()[:500]}"
        )
```

- [ ] **Step 3: Verify the file is syntactically valid (don't run yet — needs hardware)**

Run:
```bash
cd ~/robot-md/cli && python -c "import ast; ast.parse(open('tests/hardware/test_sp1_demo_path.py').read())" && echo "✓ valid Python"
```

Expected: `✓ valid Python`

- [ ] **Step 4: Commit**

Run:
```bash
cd ~/robot-md && git add cli/tests/hardware/test_sp1_demo_path.py && git commit -m "test(sp1): hardware tests for Python MCP server startup + tool list

Two @hardware-marked tests:
  1. robot-md mcp starts and exposes execute_task et al.
  2. Fresh server start succeeds (lazy path's 'after pip install' step).

Skipped in CI; runs on bob's RPi5 with /dev/ttyACM0 + ROBOT.md."
```

---

## Phase 7: Release coordination

### Task 7.1: Push the `~/robot-md-mcp` changes (plugin)

- [ ] **Step 1: Verify all robot-md-mcp commits are local-only**

Run:
```bash
cd ~/robot-md-mcp && git log --oneline origin/main..HEAD
```

Expected: 3 commits (mcp.json change, plugin.json description, SKILL.md motion-intent stanza). If unexpected commits present, review them.

- [ ] **Step 2: Push to origin**

Run:
```bash
cd ~/robot-md-mcp && git push origin main
```

Expected: push succeeds.

- [ ] **Step 3: Confirm Claude Code plugin marketplace re-fetches**

In a separate Claude Code session (or after restart), run:
```
/plugin update robot-md
```

Expected: plugin updates. Check `~/.claude/plugins/cache/robotregistryfoundation/robot-md/` for a newer hash directory than the previous (`9dae4897df3c` per session memory).

If `/plugin update` doesn't pick up the change, manually unregister and re-register:
```
/plugin uninstall robot-md
/plugin install robot-md
```

### Task 7.2: Tag and release `~/robot-md` to PyPI

- [ ] **Step 1: Verify all robot-md commits ready for release**

Run:
```bash
cd ~/robot-md && git log --oneline origin/main..HEAD
```

Expected: ~5-7 commits covering Phases 3-6 of this plan.

- [ ] **Step 2: Bump version in pyproject.toml**

Read current version:
```bash
grep "^version" ~/robot-md/cli/pyproject.toml
```

Edit `~/robot-md/cli/pyproject.toml` to bump version (e.g., `1.1.1` → `1.2.0` since this is a feature change).

- [ ] **Step 3: Update CHANGELOG**

Edit `~/robot-md/CHANGELOG.md` to add an entry:

```markdown
## 1.2.0 — 2026-04-27

### Changed
- **SP1: One MCP server.** The `robot-md` plugin's `.mcp.json` now declares
  the Python `robot-md mcp` server directly. Plugin requires
  `pip install 'robot-md[hardware]'`. Drops the npm `robot-md-mcp@^0.3`
  fallback path. ([SP1 spec](docs/superpowers/specs/2026-04-26-sp1-wire-python-mcp-server-design.md), [revisions](docs/superpowers/specs/2026-04-27-sp1-5-simplification-revisions.md))
- `init`'s `install_mcp` phase deprecated to a no-op. Returns
  `PhaseResult(status="skipped", ...)`. Backward-compat: signature unchanged.
- `init` emits a closing-line hint when the manifest declares motion
  capabilities (`arm.*`, `nav.*`, `gripper.*`, `perceive.*`):
  `Motion capabilities declared. To enable runtime control: pip install 'robot-md[hardware]'`.

### Added
- `using-robot-md` skill: motion-intent stanza for the lazy-discovery
  path. When operator requests motion AND `execute_task` tool is missing,
  skill halts and prints the upgrade instructions.

### Migration
- Existing manifests continue to work unchanged.
- Existing operators: `pip install --upgrade robot-md` then
  `/plugin update robot-md`. No re-init required.
```

- [ ] **Step 4: Commit version bump and changelog**

Run:
```bash
cd ~/robot-md && git add cli/pyproject.toml CHANGELOG.md && git commit -m "chore(release): v1.2.0 — SP1 one-server (Python required)"
```

- [ ] **Step 5: Tag and push**

Run:
```bash
cd ~/robot-md && git tag -a v1.2.0 -m "v1.2.0 — SP1 wire Python MCP server (one-server, Python required)" && git push origin main && git push origin v1.2.0
```

Expected: both push successfully. Tag triggers the existing release workflow (`release.yml`) which publishes to PyPI.

- [ ] **Step 6: Verify PyPI publish**

Wait ~5 minutes after the tag push, then:
```bash
pip index versions robot-md
```

Expected: `1.2.0` listed at top.

If publish failed, check the GitHub Actions tab on the repo to see the workflow log.

---

## Phase 8: End-to-end verification on bob's hardware

### Task 8.1: Front-loaded path verification

- [ ] **Step 1: Fresh upgrade on bob's RPi5**

SSH to bob's RPi5. Then:
```bash
pip install --upgrade --no-cache-dir robot-md
```

Expected: 1.2.0 installed.

- [ ] **Step 2: Update plugin in Claude Code**

In Claude Code (running on bob or remote):
```
/plugin update robot-md
```

Expected: plugin updates to the new git ref.

- [ ] **Step 3: Restart Claude Code session in bob's project dir**

```bash
cd ~/bob && claude
```

- [ ] **Step 4: Verify single MCP server connected**

Type: `/mcp`

Expected:
- ONE entry: `robot-md` with status `✓ connected`.
- No `robot-md-motion` entry, no leftover npm-server entry.

If the old npm `robot-md` entry still exists with status failed, that's the OLD plugin cache — operator may need to `/plugin uninstall robot-md && /plugin install robot-md` to fully refresh.

- [ ] **Step 5: Run the SP1 hardware tests**

```bash
cd ~/robot-md/cli && pytest tests/hardware/test_sp1_demo_path.py --run-hardware -v
```

Expected: both tests pass.

- [ ] **Step 6: End-to-end pick demo (the moment of truth)**

In Claude Code at `~/bob`:

Type: `Find a red lego and place it in the bowl.`

Expected:
- Skill activates.
- Safety check: asks for arm-scope authorization.
- Authorize.
- Robot moves: vision_find → arm.pick → arm.place.
- Outcome reported.

Document the result. If it works, SP1 is done end-to-end. If it fails, capture stderr from the MCP server logs and file an issue.

### Task 8.2: Lazy-discovery path verification

- [ ] **Step 1: Simulate Python-not-installed state**

In a fresh test environment (or temporarily on bob):
```bash
pip uninstall robot-md
which robot-md  # should be empty
```

- [ ] **Step 2: Open Claude Code in `~/bob`**

```bash
cd ~/bob && claude
```

- [ ] **Step 3: Verify `/mcp` shows `robot-md` as failed**

Type: `/mcp`

Expected: `robot-md` listed with status `✗ failed` and an error mentioning command not found.

- [ ] **Step 4: Trigger motion intent**

Type: `Find a red lego.`

Expected:
- Skill activates.
- Skill detects `execute_task` is not in tool list.
- Outputs the verbatim upgrade block (pip install + which robot-md verification + /mcp Reconnect).
- Does NOT attempt any tool calls related to motion.

- [ ] **Step 5: Run the install commands and Reconnect**

In a separate shell:
```bash
pip install 'robot-md[hardware]'
which robot-md  # should resolve
```

Back in Claude Code:
```
/mcp
```

Arrow to `robot-md`. Press Enter (Reconnect).

Expected: status changes to `✓ connected`.

- [ ] **Step 6: Re-trigger motion intent**

Type: `Find a red lego and place it in the bowl.`

Expected: same as Task 8.1 Step 6 — works end-to-end.

- [ ] **Step 7: Document end-to-end success**

Write up the result in `cli/tests/manual/sp1_demo_run-<DATE>.md`:

```markdown
# SP1 demo dry-run — <YYYY-MM-DD>

## Front-loaded path
- Installation time: <minutes>
- /mcp status after install: ✓
- Pick demo result: <ok | failed with X>

## Lazy path
- Time from "find a red lego" to working motion: <minutes>
- /mcp Reconnect picked up new entry-point: <yes | no — needed restart>
- Pick demo result: <ok | failed with X>

## Issues found
- <list any UX issues, error messages, missing instructions>
```

- [ ] **Step 8: Commit the dry-run documentation**

Run:
```bash
cd ~/robot-md && git add cli/tests/manual/sp1_demo_run-*.md && git commit -m "docs(sp1): record end-to-end demo dry-run results"
```

---

## Done — what's shipped

- Plugin's `.mcp.json` declares Python `robot-md mcp` (one server).
- Plugin description tells operators about the Python prereq.
- `using-robot-md` skill has motion-intent stanza for lazy discovery.
- `init` no longer shells out to `claude mcp add`.
- `init` emits motion-extras hint when relevant.
- Tests cover the deprecation, the hint, and the no-shell-out invariant.
- Hardware tests for both demo paths.
- Manual smoke checklist for skill text validation.
- Release: `robot-md` v1.2.0 on PyPI, plugin git ref pushed for marketplace re-fetch.

## Blocked dependencies (handle in their own SPs)

- **SP2** can begin once SP1 is verified on bob.
- **SP3, SP4, SP5** can begin in any order after SP1 lands.

## Open Questions resolved during implementation

- **SP1 Open Q #2 (plugin re-submission cadence):** confirmed — `/plugin update robot-md` (or marketplace auto-refresh on next session) picks up new git ref without form re-submission.
- **SP1 Open Q #3 (`/mcp` Reconnect on stdio):** verify in Phase 8 Task 8.2 Step 5. If broken, document the workaround in CHANGELOG and update the skill text to instruct restart instead.
