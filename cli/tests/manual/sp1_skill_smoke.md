# SP1 Skill Smoke Checklist

Run before SP1 release to validate the motion-intent stanza behaves correctly.
The skill text is prompt-engineering; not unit-testable.

## Setup

1. Fresh test environment (Docker container or VM):
   - Claude Code installed.
   - `robot-md` plugin installed (`claude plugin install robot-md`).
   - **No** `pip install robot-md` yet (intentionally — we test the lazy path first).
   - cwd contains a valid `ROBOT.md` with motion capabilities (use bob's or `examples/bob/ROBOT.md`).

2. Start Claude Code in that directory: `claude`.

3. Verify the plugin's `robot-md` MCP server appears in `/mcp` as `✗ failed`
   (because `robot-md` Python CLI is not on PATH).

## Smoke tests

Mark ✓/✗ as you run.

### 1. Motion intent → upgrade hint

Type to Claude: `Find a red lego and place it in the bowl.`

Expected:
- [ ] Skill activates (using-robot-md).
- [ ] Skill detects `execute_task` tool is NOT in available tools.
- [ ] Output mentions `pip install 'robot-md[hardware]'`.
- [ ] Output mentions `/mcp` → arrow to `robot-md` → Reconnect.
- [ ] Output mentions `which robot-md` verification step.
- [ ] Skill does NOT attempt motion via wrong tools.
- [ ] Skill does NOT silently fall back to manifest reads.

### 2. Documentation lookup → no false positive

Type: `Find the docs for arm.pick.`

Expected:
- [ ] Skill activates (using-robot-md).
- [ ] Skill does NOT print the upgrade hint.
- [ ] Skill answers from manifest tools (`render` or `frontmatter` resource).

### 3. Manifest read intent → no false positive

Type: `What can this robot do?`

Expected:
- [ ] Skill answers via `capabilities` resource.
- [ ] No upgrade hint.

### 4. Post-upgrade recovery

In a separate shell:
```
pip install 'robot-md[hardware]'
```

Then in Claude Code:
- `/mcp`
- arrow to `robot-md`
- Reconnect.

Verify:
- [ ] `/mcp` shows `robot-md` as `✓ connected`.
- [ ] Tool list now includes `execute_task`, `execute_capability`, `vision_find`, `estop`, `validate`, `render`, `doctor_summary`.

Type: `Find a red lego and place it in the bowl.`

Expected:
- [ ] Skill activates.
- [ ] Skill checks safety (HiTL gate for `arm` scope).
- [ ] Asks operator for authorization.
- [ ] After authorization: calls `execute_task`.
- [ ] Robot moves (verify physically).

## Perception-only tests (post-Phase 2 perceive.* fix)

### 5. Perception intent → upgrade hint

(Pre-install state.) Type: `Look at the workspace and tell me what you see.`

Expected:
- [ ] Skill detects perception intent (`look`/`see` verbs OR `perceive.*` capability check).
- [ ] Output mentions upgrade instructions same as test 1.

## If any test fails

File an issue:
- Path: `docs/superpowers/specs/2026-04-26-sp1-wire-python-mcp-server-design.md`
- Include: failing test number, observed behavior, screenshots/transcript.
