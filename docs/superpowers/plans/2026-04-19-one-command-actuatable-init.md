# One-command actuatable init — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold MCP install, skill install, and zero/sign calibration into `robot-md init` as best-effort phases, so a bare `robot-md init bob --preset so-arm101` on TTY + hardware produces an actuatable robot in one command.

**Architecture:** Thin orchestrator (`init.default_flow`) over a new `init_phases/` package where each phase returns a uniform `PhaseResult(status=ok|skipped|failed, message, detail)`. Each phase wraps an existing library function (`skill.install`, `cli_calibrate_{zero,sign}`, `cli_register`) plus one new shell-out to `claude mcp add`. Non-fatal failures are tallied; only manifest-write failure aborts. Scripted callers use `--non-interactive` to preserve today's behavior.

**Tech Stack:** Python 3.10+, Typer CLI, pytest, ruamel.yaml for in-place manifest rewrites, `feetech_servo_sdk` (already used by calibrate.py), standard-library `subprocess` / `shutil.which` for the `claude mcp add` shell-out.

**Spec:** `docs/superpowers/specs/2026-04-19-one-command-actuatable-init-design.md`

---

## File structure

### Created

- `cli/src/robot_md/init_phases/__init__.py` — exports `PhaseResult` and phase functions.
- `cli/src/robot_md/init_phases/write_manifest.py` — phase: write ROBOT.md from preset + scan.
- `cli/src/robot_md/init_phases/register.py` — phase: mint RRN via `cli_register`.
- `cli/src/robot_md/init_phases/install_mcp.py` — phase: register stdio MCP with Claude Code.
- `cli/src/robot_md/init_phases/install_skill.py` — phase: drop skill into `~/.claude/skills/`.
- `cli/src/robot_md/init_phases/calibrate_sign.py` — phase: wrap `cli_calibrate_sign` with TTY/hardware pre-flight.
- `cli/src/robot_md/init_phases/calibrate_zero.py` — phase: wrap `cli_calibrate_zero` with TTY/hardware pre-flight.
- `cli/src/robot_md/install_mcp_claude_code.py` — subprocess wrapper around `claude mcp add`.
- `cli/tests/unit/test_init_phase_install_mcp.py`
- `cli/tests/unit/test_init_phase_install_skill.py`
- `cli/tests/unit/test_init_phase_calibrate_zero.py`
- `cli/tests/unit/test_init_phase_calibrate_sign.py`
- `cli/tests/unit/test_init_phase_register.py`
- `cli/tests/unit/test_init_phase_write_manifest.py`
- `cli/tests/unit/test_install_mcp_claude_code.py`
- `cli/tests/unit/test_init_non_interactive.py`
- `cli/tests/integration/test_init_default_flow.py`
- `cli/tests/hardware/test_init_e2e_feetech.py`

### Modified

- `cli/src/robot_md/init.py` — adds `default_flow()` orchestrator and `non_interactive()` (renamed from `quick`); `wizard()` becomes alias to `default_flow`.
- `cli/src/robot_md/__main__.py:170-358` — new flags, routes to `default_flow()` by default.
- `cli/src/robot_md/claude_md.py` (inline template `_TEMPLATE_INLINE`) + `integrations/claude-code/CLAUDE.md.template` — refresh to list all six MCP tools and update the motion-action row.
- `cli/tests/test_init.py` — rename `test_quick_*` → `test_non_interactive_*`; keep assertions unchanged.
- `cli/tests/test_claude_md.py` — assert new template content (execute_capability, estop, execute_task).
- `README.md` — one paragraph on the new default behavior.
- `CHANGELOG.md` — v0.5.0 entry.
- `docs/getting-started-claude-code.md` — post-init flow.

---

## Task 1: `PhaseResult` dataclass and `init_phases` package skeleton

**Files:**
- Create: `cli/src/robot_md/init_phases/__init__.py`
- Test: `cli/tests/unit/test_init_phase_install_mcp.py` (imports from the package to prove it exists)

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_install_mcp.py`:

```python
"""Package-import smoke test for init_phases."""
from __future__ import annotations


def test_phase_result_exports():
    from robot_md.init_phases import PhaseResult

    r = PhaseResult(phase="x", status="ok", message="ok", detail=None)
    assert r.phase == "x"
    assert r.status == "ok"
    assert r.message == "ok"
    assert r.detail is None


def test_phase_result_accepts_skipped_and_failed():
    from robot_md.init_phases import PhaseResult

    assert PhaseResult(phase="x", status="skipped", message="m", detail=None).status == "skipped"
    assert PhaseResult(phase="x", status="failed", message="m", detail={"e": 1}).detail == {"e": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_mcp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robot_md.init_phases'`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/__init__.py`:

```python
"""Per-phase functions used by `robot-md init` orchestrator.

Each phase is independently callable and returns a uniform `PhaseResult`.
Phases never raise, except `phase_write_manifest` which is allowed to
raise on truly fatal I/O errors (disk full, refuse-to-overwrite).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PhaseStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: PhaseStatus
    message: str
    detail: dict | None


__all__ = ["PhaseResult", "PhaseStatus"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_mcp.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_install_mcp.py
git commit -m "$(cat <<'EOF'
feat(init_phases): introduce PhaseResult + empty phase package

Foundation for the one-command actuatable init flow — subsequent tasks
add phase functions (install_mcp, install_skill, calibrate_{zero,sign},
register, write_manifest).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `install_mcp_claude_code.py` — subprocess wrapper around `claude mcp add`

**Files:**
- Create: `cli/src/robot_md/install_mcp_claude_code.py`
- Test: `cli/tests/unit/test_install_mcp_claude_code.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_install_mcp_claude_code.py`:

```python
"""Unit tests for the claude-mcp-add subprocess wrapper."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def test_add_returns_failed_when_claude_not_in_path(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    with patch("robot_md.install_mcp_claude_code.shutil.which", return_value=None):
        result = add("robot-md-bob", manifest)

    assert result.status == "failed"
    assert "claude" in result.message.lower()
    assert result.detail and result.detail.get("reason") == "claude_not_in_path"


def test_add_returns_ok_on_successful_subprocess(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="Added", stderr="")
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake) as run,
    ):
        result = add("robot-md-bob", manifest, command="robot-md-mcp")

    assert result.status == "ok"
    assert result.detail and result.detail.get("server_name") == "robot-md-bob"
    args = run.call_args.args[0]
    # claude mcp add <name> <cmd> <arg1> ...
    assert args[0] == "/usr/bin/claude"
    assert "mcp" in args and "add" in args
    assert "robot-md-bob" in args
    assert "robot-md-mcp" in args
    assert str(manifest) in args


def test_add_treats_already_registered_as_ok(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr="server with name 'robot-md-bob' already exists",
    )
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake),
    ):
        result = add("robot-md-bob", manifest)

    assert result.status == "ok"
    assert result.detail and result.detail.get("already_registered") is True


def test_add_returns_failed_on_other_subprocess_error(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(
        args=[],
        returncode=2,
        stdout="",
        stderr="unexpected failure",
    )
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake),
    ):
        result = add("robot-md-bob", manifest)

    assert result.status == "failed"
    assert "unexpected" in result.message or "failed" in result.message


def test_add_scope_passed_through(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake) as run,
    ):
        add("robot-md-bob", manifest, scope="user")

    args = run.call_args.args[0]
    assert "--scope" in args
    assert args[args.index("--scope") + 1] == "user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_install_mcp_claude_code.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'robot_md.install_mcp_claude_code'`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/install_mcp_claude_code.py`:

```python
"""Thin wrapper around `claude mcp add` for `robot-md init --install-mcp`.

Shells out via subprocess. Detects `claude` missing from PATH and
"already registered" as non-errors (returns ok). Never raises.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from robot_md.init_phases import PhaseResult

Scope = Literal["local", "user", "project"]


def add(
    server_name: str,
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """Register a stdio MCP server with Claude Code via `claude mcp add`.

    Idempotent: if the server is already registered at this scope,
    returns `status="ok"` with `detail["already_registered"] = True`.
    Returns `status="failed"` with a clear message if the `claude` CLI
    is not available or the subprocess fails for another reason.
    """
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message="`claude` CLI not in PATH — install Claude Code or run "
            f"`claude mcp add {server_name} -- {command} {manifest_path}` manually.",
            detail={"reason": "claude_not_in_path"},
        )

    args = [
        claude_bin,
        "mcp",
        "add",
        server_name,
        "--scope",
        scope,
        "--",
        command,
        str(manifest_path),
    ]

    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
    except OSError as e:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message=f"subprocess failed to launch `claude`: {e}",
            detail={"reason": "subprocess_exec_failed", "error": str(e)},
        )

    if proc.returncode == 0:
        return PhaseResult(
            phase="install_mcp",
            status="ok",
            message=f"registered '{server_name}' ({scope} scope)",
            detail={"server_name": server_name, "scope": scope, "already_registered": False},
        )

    combined = (proc.stderr or "") + (proc.stdout or "")
    if "already exists" in combined.lower() or "already registered" in combined.lower():
        return PhaseResult(
            phase="install_mcp",
            status="ok",
            message=f"'{server_name}' already registered ({scope} scope)",
            detail={"server_name": server_name, "scope": scope, "already_registered": True},
        )

    return PhaseResult(
        phase="install_mcp",
        status="failed",
        message=f"`claude mcp add` failed (exit {proc.returncode}): {combined.strip()[:200]}",
        detail={
            "reason": "claude_add_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr,
            "stdout": proc.stdout,
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_install_mcp_claude_code.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/install_mcp_claude_code.py cli/tests/unit/test_install_mcp_claude_code.py
git commit -m "$(cat <<'EOF'
feat(install_mcp_claude_code): subprocess wrapper for `claude mcp add`

Used by the init orchestrator's install_mcp phase. Treats "claude not
in PATH" and "already registered" as recoverable — returns PhaseResult
rather than raising, so init can tally and continue.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `phase_install_mcp` — wrap `install_mcp_claude_code.add`

**Files:**
- Create: `cli/src/robot_md/init_phases/install_mcp.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py` (export `phase_install_mcp`)
- Test: `cli/tests/unit/test_init_phase_install_mcp.py` (extend from Task 1)

- [ ] **Step 1: Write the failing test**

Append to `cli/tests/unit/test_init_phase_install_mcp.py`:

```python
from pathlib import Path
from unittest.mock import patch


def test_phase_install_mcp_derives_server_name_from_robot_name(tmp_path):
    from robot_md.init_phases import phase_install_mcp, PhaseResult

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\nmetadata:\n  robot_name: bob\n---\n\n# bob\n"
    )

    fake_result = PhaseResult(
        phase="install_mcp",
        status="ok",
        message="registered 'robot-md-bob'",
        detail={"server_name": "robot-md-bob", "scope": "local", "already_registered": False},
    )
    with patch("robot_md.init_phases.install_mcp.add", return_value=fake_result) as add:
        result = phase_install_mcp(manifest)

    assert result.status == "ok"
    assert add.call_args.args[0] == "robot-md-bob"
    assert add.call_args.args[1] == manifest


def test_phase_install_mcp_returns_failed_when_manifest_missing_name(tmp_path):
    from robot_md.init_phases import phase_install_mcp

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n\n# robot\n")

    result = phase_install_mcp(manifest)
    assert result.status == "failed"
    assert "robot_name" in result.message.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_mcp.py -v`
Expected: the two new tests FAIL with `ImportError: cannot import name 'phase_install_mcp'`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/install_mcp.py`:

```python
"""Phase: register the stdio MCP server with Claude Code."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.install_mcp_claude_code import Scope, add
from robot_md.parser import parse_file


def phase_install_mcp(
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """Derive the MCP server name from the manifest and delegate to `add`.

    Server name is `robot-md-<robot_name>` so multiple robots coexist
    cleanly in one `~/.claude.json`. Returns a `PhaseResult`; never raises.
    """
    try:
        parsed = parse_file(manifest_path)
    except Exception as e:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message=f"could not read manifest {manifest_path}: {e}",
            detail={"reason": "parse_error", "error": str(e)},
        )

    robot_name = (parsed.frontmatter.get("metadata") or {}).get("robot_name")
    if not robot_name:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message="manifest has no metadata.robot_name; cannot derive server name",
            detail={"reason": "missing_robot_name"},
        )

    server_name = f"robot-md-{robot_name}"
    return add(server_name, manifest_path, command=command, scope=scope)
```

Update `cli/src/robot_md/init_phases/__init__.py` to expose it:

```python
"""Per-phase functions used by `robot-md init` orchestrator.

Each phase is independently callable and returns a uniform `PhaseResult`.
Phases never raise, except `phase_write_manifest` which is allowed to
raise on truly fatal I/O errors (disk full, refuse-to-overwrite).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PhaseStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: PhaseStatus
    message: str
    detail: dict | None


from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402

__all__ = ["PhaseResult", "PhaseStatus", "phase_install_mcp"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_mcp.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/install_mcp.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_install_mcp.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_install_mcp

Thin wrapper around install_mcp_claude_code.add that derives the MCP
server name from metadata.robot_name (form: robot-md-<robot_name>).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `phase_install_skill` — wrap `skill.install`

**Files:**
- Create: `cli/src/robot_md/init_phases/install_skill.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py` (export)
- Test: `cli/tests/unit/test_init_phase_install_skill.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_install_skill.py`:

```python
"""Unit tests for phase_install_skill."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_ok_returns_installed_path(tmp_path):
    from robot_md.init_phases import phase_install_skill

    skills_dir = tmp_path / "skills"
    target = skills_dir / "using-robot-md" / "SKILL.md"
    with patch("robot_md.init_phases.install_skill.skill_install", return_value=target) as inst:
        result = phase_install_skill(dest_root=skills_dir)

    assert result.status == "ok"
    assert result.detail and str(target) == result.detail.get("path")
    assert inst.call_args.kwargs.get("dest_root") == skills_dir


def test_already_installed_returns_ok_with_note(tmp_path):
    from robot_md.init_phases import phase_install_skill

    skills_dir = tmp_path / "skills"

    def raise_exists(*_, **__):
        raise FileExistsError("already there")

    with patch("robot_md.init_phases.install_skill.skill_install", side_effect=raise_exists):
        result = phase_install_skill(dest_root=skills_dir)

    assert result.status == "ok"
    assert result.detail and result.detail.get("already_installed") is True


def test_permission_error_returns_failed(tmp_path):
    from robot_md.init_phases import phase_install_skill

    with patch(
        "robot_md.init_phases.install_skill.skill_install",
        side_effect=PermissionError("nope"),
    ):
        result = phase_install_skill(dest_root=tmp_path / "skills")

    assert result.status == "failed"
    assert "permission" in result.message.lower() or "nope" in result.message.lower()


def test_filenotfound_skill_content_returns_failed(tmp_path):
    from robot_md.init_phases import phase_install_skill

    with patch(
        "robot_md.init_phases.install_skill.skill_install",
        side_effect=FileNotFoundError("SKILL.md missing from wheel"),
    ):
        result = phase_install_skill(dest_root=tmp_path / "skills")

    assert result.status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_skill.py -v`
Expected: FAIL with `ImportError: cannot import name 'phase_install_skill'`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/install_skill.py`:

```python
"""Phase: install the using-robot-md skill into the operator's skills dir."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.skill import install as skill_install


def phase_install_skill(
    *,
    dest_root: Path | None = None,
    force: bool = True,
) -> PhaseResult:
    """Install the using-robot-md skill. Idempotent with force=True (default)."""
    try:
        path = skill_install(dest_root=dest_root, force=force)
    except FileExistsError as e:
        return PhaseResult(
            phase="install_skill",
            status="ok",
            message=f"skill already installed — {e}",
            detail={"already_installed": True},
        )
    except FileNotFoundError as e:
        return PhaseResult(
            phase="install_skill",
            status="failed",
            message=f"bundled skill content missing: {e}",
            detail={"reason": "skill_content_missing", "error": str(e)},
        )
    except PermissionError as e:
        return PhaseResult(
            phase="install_skill",
            status="failed",
            message=f"permission denied installing skill: {e}",
            detail={"reason": "permission_error", "error": str(e)},
        )

    return PhaseResult(
        phase="install_skill",
        status="ok",
        message=f"installed at {path}",
        detail={"path": str(path), "already_installed": False},
    )
```

Update `cli/src/robot_md/init_phases/__init__.py`:

```python
"""Per-phase functions used by `robot-md init` orchestrator.

Each phase is independently callable and returns a uniform `PhaseResult`.
Phases never raise, except `phase_write_manifest` which is allowed to
raise on truly fatal I/O errors (disk full, refuse-to-overwrite).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PhaseStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: PhaseStatus
    message: str
    detail: dict | None


from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402

__all__ = ["PhaseResult", "PhaseStatus", "phase_install_mcp", "phase_install_skill"]
```

**Note on force=True:** `skill.install` defaults force=False (raises on existing). Phase defaults force=True so re-running init overwrites with the latest skill content — analogous to re-running `pip install`. Tests mock `skill_install` directly, so the behavior is explicit.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_install_skill.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/install_skill.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_install_skill.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_install_skill

Wraps skill.install with PhaseResult semantics. Treats FileExistsError
as ok (already installed); permission / missing-content as failed.
Defaults force=True so re-running init refreshes the skill content.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `phase_calibrate_zero` — wrap `cli_calibrate_zero` with TTY/hardware pre-flight

**Files:**
- Create: `cli/src/robot_md/init_phases/calibrate_zero.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py`
- Test: `cli/tests/unit/test_init_phase_calibrate_zero.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_calibrate_zero.py`:

```python
"""Unit tests for phase_calibrate_zero — TTY/hardware gates + success/failure paths."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _write_feetech_manifest(path: Path) -> None:
    path.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "drivers:\n  - id: arm\n    protocol: feetech\n    port: /dev/ttyACM0\n"
        "---\n\n# bob\n"
    )


def test_skipped_when_stdin_not_tty(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=False):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "tty" in result.message.lower()


def test_skipped_when_hardware_absent(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=False),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "hardware" in result.message.lower() or "/dev/ttyACM0" in result.message


def test_skipped_when_operator_declines(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="n"),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "declined" in result.message.lower() or "skip" in result.message.lower()


def test_ok_runs_cli_calibrate_zero(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=0) as run,
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "ok"
    run.assert_called_once_with(str(manifest))


def test_failed_when_cli_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=1),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 1


def test_bypass_prompt_when_prompt_false(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input") as input_mock,
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=0),
    ):
        phase_calibrate_zero(manifest, prompt=False)

    input_mock.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_calibrate_zero.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/calibrate_zero.py`:

```python
"""Phase: zero-pose calibration — wraps cli_calibrate_zero with pre-flight."""

from __future__ import annotations

import sys
from pathlib import Path

from robot_md.calibrate import cli_calibrate_zero
from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file


def _probe_feetech_port(port: str, baud: int = 1_000_000) -> bool:
    """Return True if the port opens and servo id 1 responds to Present Position.

    Runs in a few hundred ms; imports feetech_servo_sdk lazily so the
    phase module is importable on systems without the hardware SDK.
    """
    try:
        from feetech_servo_sdk import PacketHandler, PortHandler  # lazy
    except Exception:
        return False
    ph = PortHandler(port)
    try:
        if not ph.openPort():
            return False
        if not ph.setBaudRate(baud):
            return False
        pk = PacketHandler(0)
        _, comm, err = pk.read2ByteTxRx(ph, 1, 56)  # servo id 1, ADDR_PRESENT
        return comm == 0 and err == 0
    except Exception:
        return False
    finally:
        try:
            ph.closePort()
        except Exception:
            pass


def _drivers(manifest_path: Path) -> list[dict]:
    try:
        parsed = parse_file(manifest_path)
    except Exception:
        return []
    return list(parsed.frontmatter.get("drivers") or [])


def phase_calibrate_zero(manifest_path: Path, *, prompt: bool = True) -> PhaseResult:
    """Run zero-pose calibration if TTY + hardware are present.

    Pre-flight:
      1. stdin.isatty() — skip if not a TTY.
      2. _probe_feetech_port — skip if the declared feetech port does not
         respond to a single servo read.
    If `prompt=True`, asks the operator Y/n before running.
    """
    if not sys.stdin.isatty():
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message="no TTY; run `robot-md calibrate --zero ROBOT.md` separately",
            detail={"reason": "no_tty"},
        )

    drivers = _drivers(manifest_path)
    if not drivers or drivers[0].get("protocol") != "feetech":
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message="no feetech driver declared; zero calibration is a no-op",
            detail={"reason": "no_feetech_driver"},
        )

    port = drivers[0].get("port") or "/dev/ttyACM0"
    baud = int(drivers[0].get("baud_rate") or drivers[0].get("baud") or 1_000_000)

    if not _probe_feetech_port(port, baud):
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message=f"no hardware detected on {port}; run `robot-md calibrate --zero ROBOT.md` "
            f"after plugging in the arm",
            detail={"reason": "no_hardware", "port": port},
        )

    if prompt:
        try:
            answer = input("Run zero-pose calibration now? [Y/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return PhaseResult(
                phase="zero_cal",
                status="skipped",
                message="operator aborted",
                detail={"reason": "aborted"},
            )
        if answer.startswith("n"):
            return PhaseResult(
                phase="zero_cal",
                status="skipped",
                message="operator declined",
                detail={"reason": "declined"},
            )

    rc = cli_calibrate_zero(str(manifest_path))
    if rc == 0:
        return PhaseResult(
            phase="zero_cal",
            status="ok",
            message="zero_pose_steps patched",
            detail={"exit_code": 0},
        )
    return PhaseResult(
        phase="zero_cal",
        status="failed",
        message=f"cli_calibrate_zero exit code {rc}",
        detail={"exit_code": rc},
    )
```

Update `cli/src/robot_md/init_phases/__init__.py` exports:

```python
from robot_md.init_phases.calibrate_zero import phase_calibrate_zero  # noqa: E402
from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402

__all__ = [
    "PhaseResult",
    "PhaseStatus",
    "phase_calibrate_zero",
    "phase_install_mcp",
    "phase_install_skill",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_calibrate_zero.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/calibrate_zero.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_calibrate_zero.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_calibrate_zero with TTY/hardware pre-flight

Skips cleanly on headless runs, missing hardware, and operator decline.
Reuses cli_calibrate_zero from robot_md.calibrate. Probes one servo via
feetech_servo_sdk to confirm the port is live before prompting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `phase_calibrate_sign` — wrap `cli_calibrate_sign` with same pre-flight

**Files:**
- Create: `cli/src/robot_md/init_phases/calibrate_sign.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py`
- Test: `cli/tests/unit/test_init_phase_calibrate_sign.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_calibrate_sign.py`:

```python
"""Unit tests for phase_calibrate_sign — same gates as zero, separate phase name."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _write_feetech_manifest(path: Path) -> None:
    path.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "drivers:\n  - id: arm\n    protocol: feetech\n    port: /dev/ttyACM0\n"
        "---\n\n# bob\n"
    )


def test_skipped_when_stdin_not_tty(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=False):
        result = phase_calibrate_sign(manifest)

    assert result.status == "skipped"
    assert result.phase == "sign_cal"


def test_skipped_when_hardware_absent(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=False),
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "skipped"


def test_ok_runs_cli_calibrate_sign(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_sign.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_sign.cli_calibrate_sign", return_value=0) as run,
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "ok"
    run.assert_called_once_with(str(manifest))


def test_failed_when_cli_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_sign.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_sign.cli_calibrate_sign", return_value=2),
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_calibrate_sign.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/calibrate_sign.py`. This is structurally a copy of `calibrate_zero.py` (not a call to it) to keep the two phases independently owned:

```python
"""Phase: encoder-sign calibration — wraps cli_calibrate_sign with pre-flight."""

from __future__ import annotations

import sys
from pathlib import Path

from robot_md.calibrate import cli_calibrate_sign
from robot_md.init_phases import PhaseResult
from robot_md.init_phases.calibrate_zero import _drivers, _probe_feetech_port


def phase_calibrate_sign(manifest_path: Path, *, prompt: bool = True) -> PhaseResult:
    """Run encoder-sign calibration if TTY + hardware are present.

    Same pre-flight as phase_calibrate_zero: stdin TTY + feetech port
    probe. Delegates to robot_md.calibrate.cli_calibrate_sign which
    wiggles each joint and asks the operator which direction it moved.
    """
    if not sys.stdin.isatty():
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message="no TTY; run `robot-md calibrate --sign ROBOT.md` separately",
            detail={"reason": "no_tty"},
        )

    drivers = _drivers(manifest_path)
    if not drivers or drivers[0].get("protocol") != "feetech":
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message="no feetech driver declared; sign calibration is a no-op",
            detail={"reason": "no_feetech_driver"},
        )

    port = drivers[0].get("port") or "/dev/ttyACM0"
    baud = int(drivers[0].get("baud_rate") or drivers[0].get("baud") or 1_000_000)

    if not _probe_feetech_port(port, baud):
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message=f"no hardware detected on {port}; run `robot-md calibrate --sign ROBOT.md` "
            f"after plugging in the arm",
            detail={"reason": "no_hardware", "port": port},
        )

    if prompt:
        try:
            answer = input("Run encoder-sign calibration now? [Y/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return PhaseResult(
                phase="sign_cal",
                status="skipped",
                message="operator aborted",
                detail={"reason": "aborted"},
            )
        if answer.startswith("n"):
            return PhaseResult(
                phase="sign_cal",
                status="skipped",
                message="operator declined",
                detail={"reason": "declined"},
            )

    rc = cli_calibrate_sign(str(manifest_path))
    if rc == 0:
        return PhaseResult(
            phase="sign_cal",
            status="ok",
            message="encoder_sign patched",
            detail={"exit_code": 0},
        )
    return PhaseResult(
        phase="sign_cal",
        status="failed",
        message=f"cli_calibrate_sign exit code {rc}",
        detail={"exit_code": rc},
    )
```

Update `cli/src/robot_md/init_phases/__init__.py` exports:

```python
from robot_md.init_phases.calibrate_sign import phase_calibrate_sign  # noqa: E402
from robot_md.init_phases.calibrate_zero import phase_calibrate_zero  # noqa: E402
from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402

__all__ = [
    "PhaseResult",
    "PhaseStatus",
    "phase_calibrate_sign",
    "phase_calibrate_zero",
    "phase_install_mcp",
    "phase_install_skill",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_calibrate_sign.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/calibrate_sign.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_calibrate_sign.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_calibrate_sign

Same TTY/hardware pre-flight as phase_calibrate_zero; delegates to
cli_calibrate_sign from robot_md.calibrate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `phase_register` — wrap `cli_register`

**Files:**
- Create: `cli/src/robot_md/init_phases/register.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py`
- Test: `cli/tests/unit/test_init_phase_register.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_register.py`:

```python
"""Unit tests for phase_register."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_ok_when_cli_register_returns_zero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n  rrn: RRN-ABC123456789\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=0) as run:
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "ok"
    assert result.detail and result.detail.get("rrn") == "RRN-ABC123456789"
    run.assert_called_once()
    assert run.call_args.kwargs.get("contact_email") == "me@acme.com"


def test_failed_when_cli_register_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=1):
        result = phase_register(manifest, contact_email="me@acme.com")

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 1


def test_passes_through_optional_overrides(tmp_path):
    from robot_md.init_phases import phase_register

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata:\n  robot_name: bob\n---\n")

    with patch("robot_md.init_phases.register.cli_register", return_value=0) as run:
        phase_register(
            manifest,
            contact_email="me@acme.com",
            manufacturer="acme",
            model="so-arm101",
            version="1.0",
            device_id="bob",
        )

    kw = run.call_args.kwargs
    assert kw["manufacturer"] == "acme"
    assert kw["model"] == "so-arm101"
    assert kw["version"] == "1.0"
    assert kw["device_id"] == "bob"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_register.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/register.py`:

```python
"""Phase: mint an RRN for the manifest via cli_register."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file
from robot_md.register import cli_register


def phase_register(
    manifest_path: Path,
    *,
    contact_email: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    version: str | None = None,
    device_id: str | None = None,
) -> PhaseResult:
    """Mint an RRN for this manifest. Returns PhaseResult; never raises.

    After a successful mint, `cli_register` has written the RRN back into
    the manifest — we read it and include it in `detail`.
    """
    rc = cli_register(
        str(manifest_path),
        manufacturer=manufacturer,
        model=model,
        version=version,
        device_id=device_id,
        contact_email=contact_email,
    )
    if rc != 0:
        return PhaseResult(
            phase="register",
            status="failed",
            message=f"cli_register exit code {rc}",
            detail={"exit_code": rc},
        )

    rrn = ""
    try:
        parsed = parse_file(manifest_path)
        rrn = str((parsed.frontmatter.get("metadata") or {}).get("rrn") or "").strip()
    except Exception:
        pass

    return PhaseResult(
        phase="register",
        status="ok",
        message=f"minted {rrn}" if rrn else "registered (RRN not yet written)",
        detail={"rrn": rrn, "exit_code": 0},
    )
```

Update `__init__.py` exports: add `phase_register`.

```python
from robot_md.init_phases.calibrate_sign import phase_calibrate_sign  # noqa: E402
from robot_md.init_phases.calibrate_zero import phase_calibrate_zero  # noqa: E402
from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402
from robot_md.init_phases.register import phase_register  # noqa: E402

__all__ = [
    "PhaseResult",
    "PhaseStatus",
    "phase_calibrate_sign",
    "phase_calibrate_zero",
    "phase_install_mcp",
    "phase_install_skill",
    "phase_register",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_register.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/register.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_register.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_register

Wraps cli_register with PhaseResult semantics. Reads the minted RRN
out of the manifest post-mint and surfaces it in detail for the tally.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `phase_write_manifest` — extract the manifest-write logic from `quick()`

**Files:**
- Create: `cli/src/robot_md/init_phases/write_manifest.py`
- Modify: `cli/src/robot_md/init_phases/__init__.py`
- Test: `cli/tests/unit/test_init_phase_write_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_phase_write_manifest.py`:

```python
"""Unit tests for phase_write_manifest — extracted from init.quick."""
from __future__ import annotations

from pathlib import Path


class _Device:
    def __init__(self, bus=None, protocol=None, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices):
        self.devices = devices
        self.cameras: list = []


def _fake_so_arm101_scan():
    return _Scan(
        [
            _Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0"),
        ]
    )


def test_writes_manifest_with_explicit_preset(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "ok"
    assert out.exists()
    text = out.read_text()
    assert "bob" in text
    assert "so-arm101" in text or "so_arm101" in text


def test_refuses_existing_file_without_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    out.write_text("old\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "exist" in result.message.lower()


def test_overwrites_with_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    out.write_text("old\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=True,
    )

    assert result.status == "ok"
    assert "old" not in out.read_text()


def test_unknown_preset_returns_failed(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="nonexistent-preset",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "not found" in result.message.lower() or "nonexistent" in result.message
    assert not out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_write_manifest.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Create `cli/src/robot_md/init_phases/write_manifest.py`:

```python
"""Phase: write ROBOT.md from preset + hardware scan."""

from __future__ import annotations

from pathlib import Path

from robot_md.init import (
    MatchResult,
    load_presets,
    merge_preset_into_draft,
    pick_best,
    render_draft,
)
from robot_md.init_phases import PhaseResult


def phase_write_manifest(
    *,
    out_path: Path,
    robot_name: str | None,
    preset_name: str | None,
    scan,
    force: bool = False,
) -> PhaseResult:
    """Write a validated ROBOT.md draft. Returns PhaseResult; never raises
    for recoverable errors. Fatal I/O errors (disk full) may still raise.
    """
    if out_path.exists() and not force:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message=f"{out_path} already exists (pass --force to overwrite)",
            detail={"reason": "exists", "path": str(out_path)},
        )

    presets = load_presets()
    if not presets:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message="no presets found in preset directory",
            detail={"reason": "no_presets"},
        )

    if preset_name:
        sel = next(
            (p for p in presets if p.name == preset_name or p.display_name == preset_name),
            None,
        )
        if sel is None:
            names = [p.display_name for p in presets]
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message=f"preset {preset_name!r} not found. Available: {names}",
                detail={"reason": "unknown_preset", "requested": preset_name},
            )
        chosen = MatchResult(preset=sel, score=100, reasons=["explicit --preset"])
    else:
        chosen = pick_best(presets, scan)
        if chosen is None:
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message="preset list empty after pick_best",
                detail={"reason": "pick_best_empty"},
            )

    import socket

    name = robot_name or f"robot-{socket.gethostname()}"
    fm = merge_preset_into_draft(chosen.preset, name, scan)
    body_hints = chosen.preset.data.get("body_hints", {}) or {}
    text = render_draft(fm, body_hints)
    out_path.write_text(text)

    return PhaseResult(
        phase="write_manifest",
        status="ok",
        message=f"wrote {out_path.name} (preset {chosen.preset.display_name})",
        detail={
            "path": str(out_path),
            "preset": chosen.preset.display_name,
            "score": chosen.score,
            "reasons": chosen.reasons,
            "robot_name": name,
        },
    )
```

Update `__init__.py` exports: add `phase_write_manifest`.

```python
from robot_md.init_phases.calibrate_sign import phase_calibrate_sign  # noqa: E402
from robot_md.init_phases.calibrate_zero import phase_calibrate_zero  # noqa: E402
from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402
from robot_md.init_phases.register import phase_register  # noqa: E402
from robot_md.init_phases.write_manifest import phase_write_manifest  # noqa: E402

__all__ = [
    "PhaseResult",
    "PhaseStatus",
    "phase_calibrate_sign",
    "phase_calibrate_zero",
    "phase_install_mcp",
    "phase_install_skill",
    "phase_register",
    "phase_write_manifest",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_phase_write_manifest.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init_phases/write_manifest.py cli/src/robot_md/init_phases/__init__.py cli/tests/unit/test_init_phase_write_manifest.py
git commit -m "$(cat <<'EOF'
feat(init_phases): add phase_write_manifest

Extracts the preset-match + merge + render logic from init.quick into
a reusable phase. Keeps `quick` intact for back-compat (Task 12 renames
it to non_interactive); the orchestrator uses this phase directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `init.default_flow` orchestrator + tally printer + CLAUDE.md refresh call

**Files:**
- Modify: `cli/src/robot_md/init.py`
- Test: `cli/tests/integration/test_init_default_flow.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/integration/test_init_default_flow.py`:

```python
"""Integration tests for the init orchestrator — all phases mocked."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.init_phases import PhaseResult


class _Device:
    def __init__(self, bus=None, protocol=None, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices=None):
        self.devices = devices or []
        self.cameras: list = []


def _ok(phase, msg="ok"):
    return PhaseResult(phase=phase, status="ok", message=msg, detail={})


def _skip(phase, msg="skipped"):
    return PhaseResult(phase=phase, status="skipped", message=msg, detail={})


def _fail(phase, msg="failed"):
    return PhaseResult(phase=phase, status="failed", message=msg, detail={})


@pytest.fixture
def fake_scan():
    return _Scan(
        [_Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0")]
    )


def test_default_flow_runs_all_phases_in_order(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    calls: list[str] = []

    def _track(name, status="ok"):
        def fn(*a, **kw):
            calls.append(name)
            return _ok(name) if status == "ok" else _skip(name)
        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", side_effect=_track("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_track("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_track("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_track("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_track("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_track("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=True,
            contact_email="me@acme.com",
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc == 0
    assert calls == [
        "write_manifest",
        "register",
        "install_mcp",
        "install_skill",
        "sign_cal",
        "zero_cal",
    ]


def test_write_manifest_failure_aborts(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    other_called: list[str] = []

    def _track(name):
        def fn(*a, **kw):
            other_called.append(name)
            return _ok(name)
        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", return_value=_fail("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_track("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_track("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_track("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_track("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_track("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=True,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc != 0
    assert other_called == []


def test_non_fatal_failures_continue_and_exit_zero(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", return_value=_ok("write_manifest")),
        patch("robot_md.init.phase_install_mcp", return_value=_fail("install_mcp")),
        patch("robot_md.init.phase_install_skill", return_value=_ok("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", return_value=_fail("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    assert rc == 0


def test_skip_flags_omit_phases(tmp_path, fake_scan):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"
    calls: list[str] = []

    def _rec(name):
        def fn(*a, **kw):
            calls.append(name)
            return _ok(name)
        return fn

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", side_effect=_rec("write_manifest")),
        patch("robot_md.init.phase_register", side_effect=_rec("register")),
        patch("robot_md.init.phase_install_mcp", side_effect=_rec("install_mcp")),
        patch("robot_md.init.phase_install_skill", side_effect=_rec("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", side_effect=_rec("sign_cal")),
        patch("robot_md.init.phase_calibrate_zero", side_effect=_rec("zero_cal")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_sign_cal=False,
            do_zero_cal=False,
        )

    assert calls == ["write_manifest"]


def test_tally_prints_one_line_per_executed_phase(tmp_path, fake_scan, capsys):
    from robot_md.init import default_flow

    out = tmp_path / "ROBOT.md"

    with (
        patch("robot_md.init.scan_system", return_value=fake_scan),
        patch("robot_md.init.phase_write_manifest", return_value=_ok("write_manifest", "wrote ROBOT.md")),
        patch("robot_md.init.phase_install_mcp", return_value=_ok("install_mcp", "registered 'robot-md-bob'")),
        patch("robot_md.init.phase_install_skill", return_value=_ok("install_skill", "installed")),
        patch("robot_md.init.phase_calibrate_sign", return_value=_skip("sign_cal", "operator declined")),
        patch("robot_md.init.phase_calibrate_zero", return_value=_ok("zero_cal", "zero_pose_steps patched")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        default_flow(
            out,
            robot_name="bob",
            preset_name="so-arm101",
            force=False,
            do_register=False,
            do_install_mcp=True,
            do_install_skill=True,
            do_sign_cal=True,
            do_zero_cal=True,
        )

    err = capsys.readouterr().err
    assert "✓ manifest" in err or "✓ write_manifest" in err
    assert "install_mcp" in err
    assert "install_skill" in err
    assert "sign_cal" in err
    assert "zero_cal" in err
    # Skipped prefix
    assert "-" in err  # dash for skipped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/integration/test_init_default_flow.py -v`
Expected: FAIL with `ImportError: cannot import name 'default_flow'`.

- [ ] **Step 3: Write minimal implementation**

Modify `cli/src/robot_md/init.py`. Append these symbols after the existing functions (keep `quick` and `wizard` intact for now; Task 12 renames them):

```python
# ---------------------------------------------------------------- orchestrator

from robot_md.init_phases import (  # noqa: E402
    PhaseResult,
    phase_calibrate_sign,
    phase_calibrate_zero,
    phase_install_mcp,
    phase_install_skill,
    phase_register,
    phase_write_manifest,
)


def _tally_line(r: PhaseResult) -> str:
    glyph = {"ok": "✓", "skipped": "-", "failed": "✗"}[r.status]
    # Human phase name: install_mcp → install-mcp, write_manifest → manifest (friendlier)
    label_map = {
        "write_manifest": "manifest    ",
        "register":       "register    ",
        "install_mcp":    "install-mcp ",
        "install_skill":  "install-skill",
        "sign_cal":       "sign-cal    ",
        "zero_cal":       "zero-cal    ",
    }
    label = label_map.get(r.phase, r.phase)
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
) -> int:
    """Run the six-phase init flow. Returns 0 unless manifest-write failed.

    Each step emits a single status line to stderr. A final tally block
    summarizes what ran, was skipped, or failed. Phase ordering is:
    manifest → register → install_mcp → install_skill → sign_cal → zero_cal.
    """
    scan = scan_system()
    results: list[PhaseResult] = []

    # Phase 1: write manifest (required)
    r_write = phase_write_manifest(
        out_path=out_path,
        robot_name=robot_name,
        preset_name=preset_name,
        scan=scan,
        force=force,
    )
    results.append(r_write)
    if r_write.status != "ok":
        _print_tally(results, out_path)
        return 2  # only fatal exit path

    # Refresh CLAUDE.md next to the new manifest.
    _refresh_claude_md(out_path)

    # Phase 2: register (opt-in)
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


def _print_tally(results: list[PhaseResult], out_path: Path) -> None:
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
    if robot_name:
        print(
            f"{robot_name} is set up. Open Claude Code in this dir:\n"
            f"  cd {out_path.parent} && claude\n",
            file=sys.stderr,
        )
```

Also add at the top of `init.py` below existing imports:

```python
import sys  # if not already imported
```

(Check `init.py` already imports `sys`; it does at line 18. No change needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/integration/test_init_default_flow.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init.py cli/tests/integration/test_init_default_flow.py
git commit -m "$(cat <<'EOF'
feat(init): add default_flow orchestrator

Walks the six phases (manifest → register → install_mcp → install_skill
→ sign_cal → zero_cal). Fatal only on manifest-write failure; every
other phase is tallied and init exits 0. Prints a ✓/-/✗ summary at end.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Wire `default_flow` into `__main__.py` init command + new flags

**Files:**
- Modify: `cli/src/robot_md/__main__.py:170-358`
- Test: `cli/tests/unit/test_init_non_interactive.py` (escape-hatch compat)

- [ ] **Step 1: Write the failing test**

Create `cli/tests/unit/test_init_non_interactive.py`:

```python
"""`robot-md init --non-interactive` preserves the old quick() behavior.

This is the scripted-caller / CI compatibility test. It must keep passing
after Task 10 wires default_flow into __main__.py.
"""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from robot_md.__main__ import app


def test_non_interactive_writes_manifest_only(tmp_path, monkeypatch):
    runner = CliRunner()
    out = tmp_path / "ROBOT.md"

    # Prevent any network or hardware access by patching the optional phases
    # to raise if they're called — the test asserts they aren't.
    import robot_md.init as init_mod

    monkeypatch.setattr(
        init_mod,
        "phase_install_mcp",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("install_mcp should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_install_skill",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("install_skill should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_calibrate_sign",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("sign_cal should not run")),
    )
    monkeypatch.setattr(
        init_mod,
        "phase_calibrate_zero",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("zero_cal should not run")),
    )

    result = runner.invoke(
        app,
        [
            "init",
            "bob",
            "--preset",
            "so-arm101",
            "--out",
            str(out),
            "--non-interactive",
            "--no-claude-md",
        ],
    )

    assert result.exit_code == 0, result.output + result.stderr if hasattr(result, "stderr") else result.output
    assert out.exists()
    text = out.read_text()
    assert "bob" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_non_interactive.py -v`
Expected: FAIL — the `--non-interactive` flag does not yet exist.

- [ ] **Step 3: Write minimal implementation**

Replace the body of the `init()` function in `cli/src/robot_md/__main__.py`. Find lines 170–358 (the current `def init(...)` command) and replace the function with this version. Keep typer imports at the top of `__main__.py` unchanged.

```python
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

      robot-md init                                      # zero prompts on headless, full flow on TTY
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
```

`default_flow` needs a new `do_refresh_claude_md` parameter so `--no-claude-md` actually gates the refresh call:

In `cli/src/robot_md/init.py`, modify `default_flow` — add parameter and gate the call:

```python
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
    ...
    # Refresh CLAUDE.md next to the new manifest.
    if do_refresh_claude_md:
        _refresh_claude_md(out_path)
    ...
```

And in `__main__.py:init`, pass `do_refresh_claude_md=with_claude_md`.

- [ ] **Step 4: Run test to verify it passes**

Run the compat test first:

Run: `cd ~/robot-md/cli && pytest tests/unit/test_init_non_interactive.py -v`
Expected: PASS.

Then the full orchestrator suite:

Run: `cd ~/robot-md/cli && pytest tests/integration/test_init_default_flow.py tests/unit/test_init_phase_*.py tests/unit/test_install_mcp_claude_code.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/__main__.py cli/src/robot_md/init.py cli/tests/unit/test_init_non_interactive.py
git commit -m "$(cat <<'EOF'
feat(cli): route `robot-md init` through default_flow

Adds --non-interactive, --no-install-mcp, --no-install-skill,
--no-sign, --no-calibrate flags. --wizard emits a one-time note that
it's now an alias for the default flow. Scripted callers use
--non-interactive to preserve the old manifest-only behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Refresh the CLAUDE.md template

**Files:**
- Modify: `cli/src/robot_md/claude_md.py` (inline `_TEMPLATE_INLINE`)
- Modify: `integrations/claude-code/CLAUDE.md.template`
- Modify: `cli/tests/test_claude_md.py`

- [ ] **Step 1: Write the failing test**

Add a new test to `cli/tests/test_claude_md.py`:

```python
def test_template_lists_all_six_mcp_tools(tmp_path):
    """CLAUDE.md should advertise the full python-MCP tool set."""
    from robot_md.claude_md import render_claude_md

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "capabilities:\n  - arm.pick\n  - arm.place\n"
        "safety:\n  hitl_gates: []\n"
        "drivers: []\n"
        "---\n\n# bob\nIdentity.\n"
    )

    text = render_claude_md(manifest)
    for tool in ("validate", "render", "estop", "execute_capability", "execute_task"):
        assert tool in text, f"expected MCP tool {tool!r} in CLAUDE.md template"


def test_template_motion_row_points_at_execute_capability(tmp_path):
    from robot_md.claude_md import render_claude_md

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\nmetadata:\n  robot_name: bob\ncapabilities: []\n"
        "safety:\n  hitl_gates: []\ndrivers: []\n---\n\n# bob\n"
    )

    text = render_claude_md(manifest)
    # The "Pick up the X" row should mention execute_capability so Claude
    # knows which tool to call for physical motion.
    assert "execute_capability" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/test_claude_md.py::test_template_lists_all_six_mcp_tools tests/test_claude_md.py::test_template_motion_row_points_at_execute_capability -v`
Expected: FAIL — current template only lists `validate` + `render` and motion row does not mention `execute_capability`.

- [ ] **Step 3: Write minimal implementation**

In `cli/src/robot_md/claude_md.py`, locate the `_TEMPLATE_INLINE` string (~line 23) and edit the two rows that are outdated.

Find:

```
| "Pick up the X" / any physical motion | This is a **hardware action**. Check `safety.hitl_gates` first. If the scope matches a gate with `require_auth: true`, stop and ask for explicit approval before issuing any command. |
```

Replace with:

```
| "Pick up the X" / any physical motion | Call `mcp__robot-md-{{ROBOT_NAME}}__execute_capability` (dry-run first). Check `safety.hitl_gates` for the cap's scope; if a gate with `require_auth: true` matches, request explicit operator approval before re-running without dry-run. |
```

Find:

```
MCP tools (also available): `validate`, `render`.
```

Replace with:

```
MCP tools (also available): `validate`, `render`, `estop`, `estop_clear`, `execute_capability`, `execute_task`.
```

Apply the same two edits to `integrations/claude-code/CLAUDE.md.template` (it's the source-of-truth template for the bundled copy).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/test_claude_md.py -v`
Expected: all tests PASS (including the two new ones and existing ones — no regressions).

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/claude_md.py integrations/claude-code/CLAUDE.md.template cli/tests/test_claude_md.py
git commit -m "$(cat <<'EOF'
docs(claude_md): advertise all six MCP tools in generated CLAUDE.md

Template previously listed only validate + render, which is stale
(the Python MCP server has exposed estop, estop_clear,
execute_capability, and execute_task since v0.3). Motion-action row
now names execute_capability so Claude knows which tool to call for
'pick up the X' intents.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Rename `quick()` → `non_interactive()` and update old tests

**Files:**
- Modify: `cli/src/robot_md/init.py` — rename function; add a thin `quick` alias that emits a deprecation warning.
- Modify: `cli/tests/test_init.py` — rename `test_quick_*` to `test_non_interactive_*`.

- [ ] **Step 1: Write the failing test**

Modify `cli/tests/test_init.py`. Rename `test_quick_writes_valid_minimal_draft` and `test_quick_writes_valid_so_arm101_draft` to `test_non_interactive_writes_valid_minimal_draft` and `test_non_interactive_writes_valid_so_arm101_draft`. Update the import:

```python
from robot_md.init import (
    PRESETS_DIR,
    Preset,
    load_presets,
    match_score,
    merge_preset_into_draft,
    non_interactive,
    pick_best,
    render_draft,
)
```

And the call sites:

```python
def test_non_interactive_writes_valid_minimal_draft(tmp_path):
    out = tmp_path / "ROBOT.md"
    rc = non_interactive(out, robot_name="bob", preset_name="minimal")
    ...


def test_non_interactive_writes_valid_so_arm101_draft(tmp_path, monkeypatch):
    ...
    rc = non_interactive(out, robot_name="bob", preset_name="so-arm101")
    ...
```

Add one new test to verify `quick` still works as a deprecation alias:

```python
def test_quick_alias_still_works_with_warning(tmp_path, capsys):
    from robot_md.init import quick

    out = tmp_path / "ROBOT.md"
    rc = quick(out, robot_name="bob", preset_name="minimal")
    assert rc == 0
    err = capsys.readouterr().err
    assert "deprecated" in err.lower() or "non_interactive" in err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/robot-md/cli && pytest tests/test_init.py -v`
Expected: all `test_non_interactive_*` tests fail with `ImportError: cannot import name 'non_interactive'`. `test_quick_alias_still_works_with_warning` fails too.

- [ ] **Step 3: Write minimal implementation**

In `cli/src/robot_md/init.py`, rename `quick` to `non_interactive` (line 270). At the bottom of the file, add a thin alias:

```python
def non_interactive(
    out_path: Path,
    *,
    robot_name: str | None = None,
    preset_name: str | None = None,
    force: bool = False,
) -> int:
    """Manifest-only init — what `quick` used to be. Preserved for --non-interactive."""
    # (paste the original quick() body here, unchanged)


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
    return non_interactive(
        out_path, robot_name=robot_name, preset_name=preset_name, force=force
    )
```

(Mechanically: take the current `quick` function body starting at line 270 and rename the `def quick` line to `def non_interactive`. Then paste the alias above below it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/robot-md/cli && pytest tests/test_init.py -v`
Expected: all tests PASS (renamed `test_non_interactive_*`, new `test_quick_alias_still_works_with_warning`, and all existing tests untouched).

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/src/robot_md/init.py cli/tests/test_init.py
git commit -m "$(cat <<'EOF'
refactor(init): rename quick → non_interactive

Keeps `quick` as a deprecated alias that emits a one-time note to
stderr. The new name reflects that this is the --non-interactive
escape hatch, not the default flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Hardware smoke test (opt-in)

**Files:**
- Create: `cli/tests/hardware/test_init_e2e_feetech.py`

- [ ] **Step 1: Write the failing test**

Create `cli/tests/hardware/test_init_e2e_feetech.py`:

```python
"""End-to-end init smoke test against a real SO-ARM101.

Opt-in: requires env var ROBOT_MD_HARDWARE=1 and a plugged-in arm on
/dev/ttyACM0. Not run in default CI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner


pytestmark = pytest.mark.skipif(
    os.environ.get("ROBOT_MD_HARDWARE") != "1",
    reason="hardware smoke test; set ROBOT_MD_HARDWARE=1 with arm plugged in",
)


def test_default_flow_writes_calibrated_manifest(tmp_path, monkeypatch):
    """A full init run should write ROBOT.md AND patch zero_pose_steps
    to the reading observed on the connected arm."""
    from robot_md.__main__ import app

    runner = CliRunner()
    out = tmp_path / "ROBOT.md"

    # Force yes-answers to the Y/n prompts; no actual skill install
    # (we don't want to touch ~/.claude/skills/ in a smoke test).
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    result = runner.invoke(
        app,
        [
            "init",
            "bob-smoke",
            "--preset",
            "so-arm101",
            "--out",
            str(out),
            "--no-install-mcp",
            "--no-install-skill",
            "--no-sign",  # sign wiggles joints — keep zero-only to minimize motion
            "--no-claude-md",
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists()
    text = out.read_text()
    # Zero pose should no longer be the default 2048 for every joint.
    # At least one joint's reading should differ from 2048 unless the
    # operator poses it at exactly 2048 on every encoder, which is
    # vanishingly unlikely.
    import yaml

    fm = yaml.safe_load(text.split("---", 2)[1])
    values = [j.get("zero_pose_steps") for j in fm["physics"]["kinematics"]]
    assert any(v != 2048 for v in values), (
        "expected at least one joint's zero_pose_steps to differ from the "
        "preset default after calibration"
    )
```

- [ ] **Step 2: Run test to verify it skips without hardware**

Run: `cd ~/robot-md/cli && pytest tests/hardware/test_init_e2e_feetech.py -v`
Expected: SKIPPED (env var not set).

Optionally, with the arm plugged in:

Run: `ROBOT_MD_HARDWARE=1 cd ~/robot-md/cli && pytest tests/hardware/test_init_e2e_feetech.py -v`
Expected: PASS when an arm is on `/dev/ttyACM0` and the operator presses Enter at the zero-pose prompt.

- [ ] **Step 3: No implementation needed (test-only task).**

- [ ] **Step 4: Run default test suite to confirm no regressions**

Run: `cd ~/robot-md/cli && pytest -v`
Expected: all pre-existing and new unit/integration tests PASS; the hardware test SKIPS.

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add cli/tests/hardware/test_init_e2e_feetech.py
git commit -m "$(cat <<'EOF'
test(init): add hardware smoke test for default_flow

Opt-in via ROBOT_MD_HARDWARE=1. Exercises the full init flow against
a real SO-ARM101 and asserts zero_pose_steps got patched from the
preset default of 2048.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: README, CHANGELOG, getting-started-claude-code.md updates

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/getting-started-claude-code.md`

- [ ] **Step 1: (docs-only — no failing test to write).** Skim the current text to plan the edits.

Run: `head -30 ~/robot-md/README.md && head -30 ~/robot-md/CHANGELOG.md && head -30 ~/robot-md/docs/getting-started-claude-code.md`

- [ ] **Step 2: README.md edit**

In `README.md`, find the "Adopt it for your robot (60 seconds)" section, specifically under "Option A — On your machine (terminal) *(recommended)*". Immediately after the existing one-liner and the "What it does:" list, add one paragraph (keep existing list intact, insert after step 7):

```markdown
**One-command actuatable:** as of v0.5.0, `robot-md init` on a TTY with the arm plugged in also installs the MCP server into Claude Code, installs the `using-robot-md` skill, and prompts Y/n for encoder-sign and zero-pose calibration. On headless runs (no TTY, or `--non-interactive`), these steps auto-skip and init degrades to the old manifest-only behavior. Individual phases can be skipped with `--no-install-mcp`, `--no-install-skill`, `--no-sign`, or `--no-calibrate`.
```

- [ ] **Step 3: CHANGELOG.md entry**

At the top of `CHANGELOG.md`, add a new v0.5.0 entry above whatever the current top section is:

```markdown
## v0.5.0 — 2026-04-19

### Added
- `robot-md init` default flow now folds MCP install, skill install, and
  zero/sign calibration into the single command. TTY + hardware detection
  gates the interactive phases; headless / CI callers auto-skip cleanly.
- New flags: `--non-interactive` (scripted callers — manifest-only),
  `--no-install-mcp`, `--no-install-skill`, `--no-sign`, `--no-calibrate`.
- New module `robot_md.install_mcp_claude_code` — subprocess wrapper around
  `claude mcp add` that returns a `PhaseResult` rather than raising.
- New package `robot_md.init_phases` — each phase of init is an independently
  callable library function returning a uniform `PhaseResult`.

### Changed
- `robot_md.init.quick` renamed to `non_interactive`; `quick` kept as a
  deprecated alias that prints a one-time note to stderr.
- `robot-md init --wizard` now an alias for the default flow (the two paths
  are identical). Emits a one-time deprecation note.
- Generated `CLAUDE.md` template now advertises all six MCP tools
  (`validate`, `render`, `estop`, `estop_clear`, `execute_capability`,
  `execute_task`) and points the motion row at `execute_capability`.

### Migration
- Scripted callers relying on `robot-md init` being non-interactive must
  add `--non-interactive`. On CI machines this is the recommended invocation.
- External code importing `robot_md.init.quick` should switch to
  `non_interactive`. The old name still works but warns on each call.
```

- [ ] **Step 4: getting-started-claude-code.md update**

In `docs/getting-started-claude-code.md`, find the section covering the `robot-md init` walk-through and append:

```markdown
### After init on a TTY with the arm plugged in

Once `robot-md init` finishes (either via the shell or the Claude-Code-driven one-liner), the robot is actuatable right away:

```bash
cd ~/your-robot-dir
claude
```

Inside Claude Code, say:

```
Dry-run pick the red lego and put it in the bowl.
```

Claude reads `CLAUDE.md`, calls `mcp__robot-md-<your_robot_name>__execute_capability(arm.pick, dry_run=true)`, shows you the trajectory, and waits for your go-ahead. Say "now actually do it" and Claude re-runs with `dry_run=false`.

### For scripted / CI callers

```bash
robot-md init bob --preset so-arm101 --non-interactive
```

Manifest-only; no prompts, no MCP or skill install, no hardware touched. Identical behavior to the pre-v0.5.0 `quick()` path.
```

- [ ] **Step 5: Commit**

```bash
cd ~/robot-md
git add README.md CHANGELOG.md docs/getting-started-claude-code.md
git commit -m "$(cat <<'EOF'
docs: v0.5.0 — one-command actuatable init

README paragraph under "Adopt it", CHANGELOG entry, and
getting-started walk-through for the new default flow and
--non-interactive escape hatch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Full-suite verification

- [ ] **Step 1: Run the entire test suite.**

Run: `cd ~/robot-md/cli && pytest -v`
Expected: all unit + integration tests PASS. Hardware test SKIPS (env var unset).

- [ ] **Step 2: Run ruff + mypy.**

Run: `cd ~/robot-md/cli && ruff check src tests && ruff format --check src tests`
Expected: no findings.

Run: `cd ~/robot-md/cli && mypy src`
Expected: no new errors vs the `main` baseline.

- [ ] **Step 3: Manual end-to-end with no hardware (sanity).**

Run: `robot-md init smoke-bot --preset so-arm101 --out /tmp/smoke/ROBOT.md --non-interactive`
Expected: manifest is written, no prompts, no network, exit 0.

Run: `robot-md init smoke-bot --preset so-arm101 --out /tmp/smoke2/ROBOT.md --no-calibrate`
Expected: manifest written, CLAUDE.md written, phase_install_mcp and phase_install_skill run, calibration phases auto-skip (no hardware), exit 0.

- [ ] **Step 4: Verify the committed git log.**

Run: `cd ~/robot-md && git log --oneline -20`
Expected: roughly 14 commits from this plan, one per task.

- [ ] **Step 5: Final sanity + merge note.**

No commit. Report the tally of commits and hand off to the user for their own merge / tag / release decisions.

---

## Self-review notes

Spec coverage walkthrough:

- ✅ Goals (actuatable in one command, marketing one-liner, library-callable phases, escape hatch, per-phase non-fatal failures) → Tasks 1–10.
- ✅ Six-phase flow with documented order → Task 9.
- ✅ Uniform `PhaseResult` → Task 1.
- ✅ `install_mcp_claude_code.py` with `shutil.which` + idempotency → Task 2.
- ✅ Each phase independently callable → Tasks 3–8.
- ✅ Pre-flight (TTY, hardware probe) for calibration → Tasks 5–6.
- ✅ CLAUDE.md template refresh → Task 11.
- ✅ `quick` → `non_interactive` with alias → Task 12.
- ✅ Hardware smoke test → Task 13.
- ✅ Docs + changelog + getting-started → Task 14.
- ✅ Full suite + lint/types → Task 15.

No placeholder / TBD / "similar to task N" patterns in the plan. All code blocks complete.

Type consistency: `PhaseResult(phase, status, message, detail)` used uniformly across all phases; `phase` values (`write_manifest`, `register`, `install_mcp`, `install_skill`, `sign_cal`, `zero_cal`) are referenced consistently from Task 1 through Task 9. Status values are the three literals in the `PhaseStatus` Literal alias.

One correction made during self-review: Task 9's `default_flow` initially didn't expose `do_refresh_claude_md` for the `--no-claude-md` flag; Task 10 surfaces the need and adds the parameter. Plan updated in-place in Task 10.
