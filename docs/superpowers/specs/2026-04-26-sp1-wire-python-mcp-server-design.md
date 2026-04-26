# SP1 — Wire the Python MCP Server (Hybrid C, Hot-Reload)

**Date:** 2026-04-26
**Status:** Design — pending implementation plan
**Sub-project:** 1 of 5 (see `2026-04-26-robot-md-runtime-decomposition.md` for the full breakdown)

## Problem

`robot-md` declares a robot's capabilities (`arm.pick`, `arm.place`, `perceive.rgb`, …), but the only MCP server currently wired into Claude Code via the `robot-md` plugin is the npm `robot-md-mcp@^0.3` server, which exposes manifest-layer tools only (`validate`, `render`, `doctor_summary`). The Python `robot-md mcp <ROBOT.md>` command, shipped in the same `robot-md` PyPI package, exposes the runtime-layer tools (`execute_task`, `execute_capability`, `vision_find`, `estop`, …) backed by `feetech_depthai` and the entry-point backend registry. **Operators have a runtime-capable MCP server installed but never connected.**

For the Anthropic acquisition demo, the story is "install plugin → ask Claude to do a thing → robot moves." Today that story breaks at "ask Claude to do a thing" — Claude can read the manifest but has no motion tools.

## Scope

**In scope:**
- Wire `robot-md mcp` (Python) as a second MCP server alongside the npm manifest server, both delivered via the existing `robot-md` plugin.
- Detect the install gap at motion-intent time and instruct the operator through the upgrade.
- Eliminate the legacy `claude mcp add` step in `robot-md init`.
- Keep the pre-session install path zero-restart; keep the lazy-discovery path one-`/mcp`-Reconnect.

**Out of scope** (handled by other sub-projects):
- Hardware autodetection → preset → backend selection (SP2).
- Manufacturer SDK adapter pattern (SP3).
- Claude-authored driver fallback (SP4).
- Gap → GitHub issue feedback loop (SP5).
- Full restart elimination via in-session reload (Claude Code limitation, not a robot-md problem).

## Design

### Architecture

Five changes across three packages:

1. **`robot-md` plugin `.mcp.json`** (in the plugin marketplace submission source) — add a second MCP server entry `robot-md-motion` pointing to the Python CLI's `robot-md mcp` command, which auto-discovers `ROBOT.md` by walking up from cwd.
2. **`robot-md/cli/src/robot_md/init.py`** — surface a `pip install 'robot-md[feetech-depthai]'` hint when the manifest declares motion capabilities. Stop calling `phase_install_mcp` from the default flow.
3. **`robot-md/cli/src/robot_md/init_phases/install_mcp.py`** — convert to a deprecation no-op returning `PhaseResult(status="skipped", ...)`. Backward-compat: function signature preserved.
4. **`integrations/claude-code-skill/SKILL.md`** (the `using-robot-md` skill) — add a "motion-intent without motion tools" stanza that fires when operator requests motion AND `execute_task` isn't in the tool surface. Skill emits a verbatim upgrade block and stops.
5. **`robot-md-mcp/src/server.ts`** (npm v0.3 → v0.3.1) — append a motion-upgrade hint to the MCP server `instructions` payload sent to clients on connect (Banner D). The plugin's `.mcp.json` pins `^0.3`, so this npm publish flows through to operators automatically without a plugin re-submission. (The plugin re-submission is needed only for change #1 — the `.mcp.json` itself.)

**Post-upgrade topology (additive coexistence, locked in):** Workspace-scope `robot-md` (npm, manifest-only) + plugin-declared `robot-md-motion` (Python, runtime + manifest). Tool overlap on `validate`/`render`/`doctor_summary` is benign — both servers read the same `ROBOT.md` via cwd-walk.

### Components

#### 1. Plugin `.mcp.json`

```json
{
  "robot-md": {
    "command": "npx",
    "args": ["-y", "robot-md-mcp@^0.3"]
  },
  "robot-md-motion": {
    "command": "robot-md",
    "args": ["mcp"]
  }
}
```

The Python `robot-md mcp` command (already implemented at `cli/src/robot_md/__main__.py:1842`) walks up from cwd to find `ROBOT.md`. Claude Code spawns plugin MCPs with the project directory as cwd, so this works when the operator opens a project containing a manifest. If no manifest is found, the server exits cleanly with informative stderr and the plugin shows ✗ failed in `/mcp`.

**Open item:** locate the source-of-truth for the plugin's `.mcp.json`. The cached plugin at `~/.claude/plugins/cache/robotregistryfoundation/robot-md/<hash>/.mcp.json` is a derivative; the canonical pre-submission file lives elsewhere (likely in `robot-md-mcp/dist/` or a sibling repo). Resolve before implementation.

#### 2. `init.py` — motion-extras hint

After the manifest is written, scan declared `capabilities[]`. If any entry matches a motion-relevant prefix (`arm.*`, `nav.*`, `gripper.*`, `perceive.*`), emit a closing line:

> Motion capabilities detected. To enable runtime control:
>
> ```
> pip install 'robot-md[feetech-depthai]'
> ```
>
> Then in Claude Code: `/mcp` → Reconnect `robot-md-motion`, or restart Claude Code.

Manifests with no motion capabilities (e.g., compute-only or sensor-aggregation robots) get no hint. Init's default flow stops invoking `phase_install_mcp`.

#### 3. `install_mcp.py` — deprecation no-op

```python
def phase_install_mcp(manifest_path, *, command="robot-md-mcp", scope="local"):
    return PhaseResult(
        phase="install_mcp",
        status="skipped",
        message="The robot-md plugin auto-registers the Python MCP server. "
                "No per-robot `claude mcp add` needed. "
                "Run `/mcp` → Reconnect `robot-md-motion` after `pip install` "
                "(or restart Claude Code).",
        detail={"deprecated_in": "1.2.0", "reason": "plugin_handles_mcp"},
    )
```

Module-level docstring marked deprecated. `install_mcp_claude_code.py` stays — useful for non-plugin operators who explicitly call it.

#### 4. `using-robot-md` SKILL.md — motion-intent stanza

Inserted near the top of the skill, after the routing table:

> ### Motion intent without motion tools
>
> If the operator requests physical motion (any of `arm.*`, `nav.*`, `gripper.*` capabilities, or English phrasing like "find / move / grasp / place / pick up / put"), AND the `execute_task` tool is NOT in your available tools, **stop before issuing any action**. Output the upgrade instructions verbatim:
>
> > "Bob has motion capabilities declared, but the Python runtime isn't installed in this environment. To enable motion:
> >
> > 1. `pip install 'robot-md[feetech-depthai]'`
> > 2. (Verify with `which robot-md` first.)
> > 3. In Claude Code: `/mcp` → arrow to `robot-md-motion` → Reconnect.
> >
> > Then ask me again."
>
> Wait for the operator to confirm. Do NOT attempt manifest reads as a substitute for motion. Do NOT attempt motion via wrong tools.
>
> **False-positive guard:** Documentation lookups (`find docs`, `find the file`, `find the README`) are NOT motion intent — proceed normally with manifest tools.

The detection mechanism is Claude's own tool-list awareness (tools are in the system prompt). No shell-out to `claude mcp list`.

#### 5. npm `robot-md-mcp/src/server.ts` — instructions payload

Append to the existing `instructions` string:

> ### When motion is needed
>
> This server is manifest-only. To enable arm/perception runtime control on this robot, install the Python CLI:
>
> ```
> pip install 'robot-md[feetech-depthai]'
> ```
>
> The `robot-md-motion` plugin server (declared in this plugin's `.mcp.json`) will activate after `/mcp` → Reconnect, or on next session start.

Bump version to `0.3.1`. Plugin `.mcp.json` pins `^0.3`, so the patch is picked up on next plugin reload without re-submission.

### Data Flow

#### Path 1: Front-loaded (the demo script)

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ claude plugin install robot-md   →    Plugin installed.
                                        .mcp.json declares 2 servers.
                                        using-robot-md skill registered.

$ pip install \                    →    Python `robot-md` CLI on PATH.
    'robot-md[feetech-depthai]'         feetech-servo-sdk, depthai,
                                          opencv, pyserial installed.

$ robot-md init bob                →    ./ROBOT.md created (autodetect prefilled).
    --preset so-arm101                  Hint emitted: "Motion ready. Open
                                          Claude Code in this directory."

$ claude                           →    Session starts in ./
                                        Plugin spawns both MCP servers:
                                          • robot-md (npm)        ✓ connected
                                          • robot-md-motion       ✓ connected
                                        Skill loads (intent-triggered).

> "Find a red lego and place        →   Skill activates (motion intent + ROBOT.md).
   it in the bowl"                      Skill checks safety gates → arm scope
                                          requires_auth → asks for authorization.

> "authorized"                      →   Claude calls execute_task tool.
                                        Python server: planning/decompose.py →
                                          [perceive.rgb, arm.pick, arm.place].
                                        Each step → execute_capability →
                                          feetech_depthai backend drives
                                          /dev/ttyACM0 + OAK-D.
                                        Returns trajectory + events.
                                        Claude reports outcome to operator.
```

Total operator commands before motion: **3** (`plugin install`, `pip install`, `init`). Then natural-language motion. No `claude mcp add`, no `/mcp` reconnect, no restart.

#### Path 2: Lazy discovery (safety net)

```
Operator                                State
─────────────────────────────────────────────────────────────────
$ claude plugin install robot-md   →    Plugin installed.
                                        (no pip install yet)

$ cd ~/bob && claude               →    Session starts.
                                        Plugin spawns servers:
                                          • robot-md (npm)        ✓ connected
                                          • robot-md-motion       ✗ failed
                                            (`robot-md` not in PATH)
                                        Skill loads.

> "Find a red lego..."              →   Skill activates.
                                        Tool-surface check: execute_task NOT in
                                          tool list → motion-intent stanza fires.
                                        Skill emits upgrade block (verbatim).
                                        STOPS. No motion attempt.

$ pip install \                    →   Python CLI now on PATH.
    'robot-md[feetech-depthai]'         (Session still doesn't see it.)

> /mcp                              →   Interactive MCP UI opens.
                                        Operator arrows to robot-md-motion (failed),
                                          selects Reconnect.
                                        Server respawns; this time `robot-md mcp`
                                          launches successfully, walks up cwd,
                                          finds ROBOT.md, exposes execute_task etc.
                                        Status: ✓ connected.

> "Find a red lego..."              →   Skill re-activates. execute_task NOW in
                                          tool list. Proceeds through safety gate
                                          → execute_task → motion runs.
```

Lazy path adds **2 extra steps** vs front-loaded (`pip install` + `/mcp` Reconnect). Same conversation, no exit/restart.

### Error Handling

#### (a) Caught — structured errors from `robot-md mcp` server

The Python MCP server **must not crash** for any of these. Connect successfully, return structured tool errors:

| Failure | Where caught | Operator sees |
|---|---|---|
| No `ROBOT.md` found via cwd-walk | server startup | Clean exit with stderr `"no ROBOT.md found walking up from <cwd>"`. Plugin shows ✗ failed in `/mcp`. |
| `ROBOT.md` malformed (YAML parse error) | `parse_file()` in server init | Clean exit, stderr explains. Don't half-load. |
| No backend matches a `drivers[].protocol` | `BackendRegistry.resolve()` at tool-call time | `execute_capability` returns `{status: "error", reason: "no_backend", detail: "..."}`. |
| Hardware port missing (`/dev/ttyACM0` not found) | Backend `_open_servo_bus` | `execute_capability` returns `{status: "error", reason: "hardware_unreachable", detail: "..."}`. |
| Planner low confidence / timeout | `planning/decompose.py` (already implemented) | `execute_task` returns `{status: "blocked", error: {reason: "low_confidence"}}`. |
| HiTL gate blocks unauthorized motion | `execute_capability` checks `safety.hitl_gates[]` | Returns `{status: "blocked", reason: "auth_required", scope: "arm"}`. |

**Verification needed during implementation:** the current `mcp/server.py` is robust to startup failures (no half-load on missing/malformed manifest). If it currently raises, wrap the startup path.

#### (b) Pass-through — outside our control

| Failure | Surface |
|---|---|
| `pip install` fails | pip's own error. Init hint preemptively states `requires Python 3.10+`. |
| `claude plugin install robot-md` fails | Plugin marketplace error. Out of SP1 scope. |
| `/mcp` → Reconnect still shows ✗ failed | Most likely PATH issue — pip installed to a different env than the shell. Skill upgrade message includes `which robot-md` verification step. |
| Operator restarts Claude Code anyway | Works identically. No regression. |

#### (c) Edge cases — defensive handling

| Edge case | Defense |
|---|---|
| Tool overlap (`validate`/`render`/`doctor_summary` on both servers) | Both walk up from cwd, both read same `ROBOT.md`, outputs byte-identical. Verified by integration test. |
| Skill false positive (e.g., "find the docs") | Trigger phrasing scoped to motion verbs in object-action context AND capability names. Documentation verbs explicitly excluded with examples in skill text. |
| Skill miss (e.g., "make the arm dance") | Permissive trigger list (`arm`, `gripper`, `move`, `motion`, `actuate`). False miss → motion attempt fails through case (a). Recoverable. |
| `robot-md mcp` finds different `ROBOT.md` than expected (nested manifests) | Server logs `"using manifest at <path>"` to stderr at startup. Operator can spot mismatch in `/mcp` server logs. Documented limitation. |
| `phase_install_mcp` still called by external scripts | No-op returns `status="skipped"`. Old scripts don't break. |
| Operator without plugin marketplace (corporate, air-gapped) | Manual fallback documented in README: `claude mcp add robot-md-motion -- robot-md mcp`. SP1 still simplifies their flow. |

#### Explicit non-goals

- Auto-recovery from failed pip install.
- `robot-md doctor --check-mcp` diagnostics (could be SP2).
- Forcing a single MCP server (additive coexistence is the deliberate model).

### Testing

#### Python unit tests — `cli/tests/unit/`

| Test | Verifies |
|---|---|
| `test_init_motion_extras_hint.py` (NEW) | When manifest declares `arm.*` or `perceive.*` capability, init output contains the pip-extras hint. Empty `capabilities[]` → no hint. |
| `test_install_mcp_deprecated.py` (NEW) | `phase_install_mcp(...)` returns `PhaseResult(status="skipped", ...)`. Does NOT shell out to `claude mcp add`. Backward-compat: signature unchanged. |
| `test_mcp_server_startup.py` (UPDATE) | Server starts cleanly when given valid `ROBOT.md`; exits with non-zero + clear stderr when missing or malformed. Does NOT raise. |
| `test_mcp_cwd_walk.py` (NEW) | Server with no explicit path walks up from cwd and finds nearest `ROBOT.md`. Nested-manifest case: closest ancestor wins. |

#### Python integration tests — `cli/tests/integration/`

| Test | Verifies |
|---|---|
| `test_init_no_claude_mcp_add.py` (NEW) | Run full `init` flow with stub `claude` CLI. Assert `claude mcp add` NOT invoked. Assert `install_mcp` phase status is `"skipped"`. |
| `test_pick_red_lego_dry_run.py` (existing) | Still passes — exercises `execute_task → decompose → execute_capability` chain in dry-run mode. SP1 didn't break the motion path. |

#### TypeScript unit tests — npm `robot-md-mcp/tests/`

| Test | Verifies |
|---|---|
| `instructions.test.ts` (NEW) | The MCP `instructions` payload includes the motion-upgrade text. Snapshot-test the full string. |

#### Plugin `.mcp.json` validation

| Test | Verifies |
|---|---|
| `validate_plugin_mcp_json.py` (NEW, CI) | Loads new `.mcp.json` and validates against Claude Code's expected schema. Both `robot-md` and `robot-md-motion` entries present. |

#### Skill text — manual smoke checklist

The motion-intent stanza is prompt-engineering, not mechanically testable without an LLM eval harness. Spec defines a manual checklist at `cli/tests/manual/sp1_skill_smoke.md`:

1. Plugin-only install (no Python CLI): `claude` → "find a red lego" → expect upgrade hint, no motion attempt.
2. Plugin-only install: `claude` → "what can this robot do?" → expect manifest read, NO upgrade hint.
3. Plugin-only install: `claude` → "find the docs for arm.pick" → expect manifest read, NO upgrade hint.
4. Plugin + Python CLI installed: `claude` → "find a red lego" → expect skill checks safety, asks for authorization, then `execute_task`.

Document expected output for each. SP4 may automate via LLM eval; SP1 doesn't invest there.

#### Hardware tests — `cli/tests/hardware/`

| Test | Verifies |
|---|---|
| `test_sp1_demo_path_1_front_loaded.py` (NEW, `@hardware`) | Full Path 1 on bob's RPi5. Skipped in CI. |
| `test_sp1_demo_path_2_lazy.py` (NEW, `@hardware`) | Full Path 2 on bob's RPi5. Skipped in CI. |
| `test_pick_red_lego_post_calibrate.py` (existing) | Still passes after SP1 changes. |

#### Coverage gaps acknowledged

- `/mcp` Reconnect behavior under SP1 changes — interactive UI; not unit-testable. Manual verification only.
- Plugin marketplace re-submission flow — out of test scope; release checklist instead.
- Operator PATH confusion — manual checklist item for demo run-through.

## Open Questions

1. **Source-of-truth for plugin `.mcp.json`.** The cached plugin at `~/.claude/plugins/cache/robotregistryfoundation/robot-md/<hash>/.mcp.json` is derivative. Canonical pre-submission file likely in `robot-md-mcp/dist/` or sibling repo. **Action:** locate before starting implementation. Implementation plan blocks until resolved.
2. **Plugin re-submission cadence.** The `.mcp.json` change requires a plugin marketplace re-submission via the form at `claude.ai/settings/plugins/submit` (per project memory). **Action:** confirm timeline; coordinate with Anthropic-acquisition demo schedule.
3. **`/mcp` Reconnect behavior on stdio.** Documented to work but not personally verified for the specific case of "command-not-found at session start, then on PATH at Reconnect time." **Action:** smoke-test before relying on it in the demo.

## Success Criteria

SP1 is done when:

- [ ] All five files (plugin `.mcp.json`, `init.py`, `install_mcp.py`, `SKILL.md`, npm `server.ts`) updated and merged.
- [ ] `robot-md-mcp@0.3.1` published to npm.
- [ ] Plugin re-submission accepted (or the `.mcp.json` change verified to flow without re-submission).
- [ ] Unit + integration test suites pass.
- [ ] Manual skill smoke checklist passes 4/4.
- [ ] Hardware tests pass on bob's RPi5 for both Path 1 and Path 2.
- [ ] Demo dry-run: fresh user does `claude plugin install robot-md && pip install 'robot-md[feetech-depthai]' && robot-md init bob && claude → "find a red lego"` end-to-end without intervention. Time-to-motion under 90 seconds (excluding pip install download time).

## Sub-project Relationships

- **SP1 unblocks SP2.** With the Python MCP server reachable from Claude Code, SP2 can layer on autodetect-driven preset/backend resolution at init time.
- **SP1 is independent of SP3-5.** Each can be specced and shipped without SP1 in place; they just remain useful through the `claude mcp add` manual fallback.
- **SP1 must ship before the Anthropic demo.** Demo story depends on the front-loaded path working zero-restart.
