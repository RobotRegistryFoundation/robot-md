# Getting started inside Claude Code

> **For operators who already have Claude Code open.** You ask Claude to set up your robot; Claude does it. No terminal gymnastics, no YAML wrangling.

This is the companion path to the [**On your machine (terminal)**](../README.md#-option-a--on-your-machine-terminal-recommended) one-liner. Same result, different on-ramp.

---

## What you need

- **Claude Code** installed and authenticated. (If you don't have it: <https://claude.com/claude-code>.)
- **A project directory** for your robot (`mkdir ~/my-robot && cd ~/my-robot`).
- **Python 3.10+** and **Node 18+** available on `PATH`. (Claude Code will tell you if they aren't.)
- The robot plugged in *or* a rough idea of what it is (so Claude can pick a preset).

That's it. No pre-installed `robot-md`, no RCAN SDK, no API key. Claude does the install.

---

## The 60-second flow

**Step 1.** Open Claude Code in your robot's project directory:

```bash
cd ~/my-robot
claude
```

**Step 2.** Paste this prompt:

```
Set up a ROBOT.md for this robot. Use the so-arm101 preset. Register it
publicly at rcan.dev under manufacturer "acme" with my contact email
me@acme.com. Then add the robot-md MCP server to this session so you
have resources pointing at the file.
```

(Substitute your own preset name, manufacturer, and email.)

**Step 3.** Claude will, in order:

1. Run `pip install robot-md` (or `pipx install` — whichever your environment prefers).
2. Run `robot-md init my-bob --preset so-arm101 --register --manufacturer acme --contact-email me@acme.com`.
3. Read back the resulting `ROBOT.md` to confirm the manifest is self-consistent.
4. Print the assigned `RRN-NNNNNNNNNNNN` and its `https://rcan.dev/r/<rrn>` resolver URL.
5. Run `claude mcp add robot-md -- npx -y robot-md-mcp "$(pwd)/ROBOT.md"` — now `robot-md://` resources are live for this session.
6. Validate: read `robot-md://my-bob/frontmatter` to confirm the MCP server sees the file.

**Step 4.** Ask Claude anything about the robot:

```
What can this robot do? What are its safety gates? Which capabilities
require human-in-the-loop approval?
```

Claude answers from the MCP resources. No re-explaining, no drift.

---

## Worked example (full transcript)

```
You: Set up a ROBOT.md for this robot. Use the so-arm101 preset.
     Register it publicly at rcan.dev under manufacturer "acme"
     with contact email me@acme.com. Then add the robot-md MCP
     server to this session.

Claude: I'll do this in four steps — install the CLI, init the
        manifest with registration, wire up MCP, then verify.

        [runs: pip install robot-md]
        ✓ robot-md 0.6.3 installed

        [runs: robot-md init my-bob --preset so-arm101 --register \
               --manufacturer acme --contact-email me@acme.com]
        ✓ wrote ROBOT.md  preset: so-arm101
        ✓ my-bob (arm, 6 DoF, 5 capabilities)
        ✓ registered on rcan.dev
          RRN: RRN-000000000042
          RCAN URI: rcan://rcan.dev/acme/so-arm101/1-0/my-bob
          Public record: https://rcan.dev/r/RRN-000000000042

        [runs: claude mcp add robot-md -- npx -y robot-md-mcp \
               "$(pwd)/ROBOT.md"]
        ✓ Added stdio MCP server robot-md

        [reads: robot-md://my-bob/frontmatter]
        ✓ MCP server responding — 4 resources live
          (frontmatter, capabilities, safety, body)

        Done. Your robot is registered (RRN-000000000042) and I have
        live access to its manifest. Ask me what it can do.

You: What can this robot do?

Claude: my-bob is a 6-DOF SO-ARM101 arm. Five capabilities:
        arm.pick, arm.place, arm.reach, vision.describe,
        status.report. Max payload 0.5 kg. Software E-stop at 100
        ms. Destructive actions and unknown-surface placements gate
        on human-in-the-loop approval.
```

---

## Custom hardware (no preset match)

If Claude can't match your robot to a preset, paste this instead:

```
Set up a ROBOT.md for this robot. It's a custom 4-DOF arm on a Feetech
bus at /dev/ttyACM0, plus a USB webcam. Run the interactive wizard and
ask me the questions — I'll fill in the physics and capabilities. Don't
register yet; I want to review the draft first.
```

Claude will run `robot-md init my-bob --wizard`, relay each prompt to you, and produce a validated draft. Review it, then ask:

```
Looks good. Now register it under manufacturer "acme", contact me@acme.com.
```

Claude runs `robot-md register ROBOT.md --manufacturer acme --contact-email me@acme.com` and writes the assigned RRN back into the manifest.

---

## Physical calibration (arms only)

Once the manifest exists, ask Claude:

```
Walk me through calibrating the arm's zero pose. I'll pose the arm
physically when you tell me to.
```

Claude runs `robot-md calibrate --zero ROBOT.md`, prompts you to pose the arm, and waits. You pose, hit Enter in the Claude Code prompt, and Claude confirms the encoder readings are recorded into the manifest. Same pattern for `--hand-eye` (print one ArUco marker, place it at a known spot, Claude solves the extrinsic).

---

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

---

## What Claude is allowed to do

Claude Code honors your permission mode. In the default *accept edits* mode, it will:

- ✅ Run `pip install robot-md`, `npx robot-md-mcp`, `claude mcp add` — installation + wiring.
- ✅ Run `robot-md init / register / calibrate / validate / render` — manifest lifecycle.
- ✅ Read and edit files under your project directory.
- ⚠ **Ask before:** destructive operations (deleting registrations, `robot-md unregister <rrn>`), writing files outside the project, publishing to external registries with non-default endpoints.

If you want stricter control, start Claude Code in plan mode (`claude --permission-mode plan`) — it will present the plan first and wait for your approval before running anything.

---

## What if something goes wrong?

Ask Claude directly:

```
Something broke — run robot-md doctor and tell me what's wrong.
```

Claude runs the diagnostic verb and reports (servo port reachable, RRF/rcan.dev reachable, schema valid, keystore integrity, claude CLI present). Most issues come down to a missing permission on `/dev/ttyACM0` or an unplugged robot — `doctor` flags both.

---

## What happens next

Your robot now has:

- ✅ A validated `ROBOT.md` at the project root.
- ✅ A `CLAUDE.md` sibling (generated by `init`) — the intent→action table Claude reads at session start.
- ✅ A public identity: `RRN-NNNNNNNNNNNN`, resolvable at `https://rcan.dev/r/<rrn>`.
- ✅ A live MCP server in this Claude Code session — six `robot-md://` resources, three tools (`validate`, `render`, `doctor_summary`), four slash commands (`/brief-me`, `/check-safety`, `/explain-capability`, `/manifest-status`).

From here, Claude Code is the planner *and* executor. Ask it to pick-and-place, describe the scene, report status — every ask routes through the safety gates declared in the manifest. No separate runtime to stand up.

**Try these next:**

- `/brief-me` — get a concise briefing on the robot.
- `/check-safety action="pick up the red cup"` — before issuing any motion, cross-check the action against declared HITL gates.
- Ask Claude: *"Run `robot-md doctor --path ROBOT.md` and tell me what's wrong."* — diagnostic across install, manifest, network, drivers, keystore.

**Want Claude on more surfaces?**

- **Claude Desktop** (macOS/Windows app): `robot-md install-desktop ROBOT.md` — merges a `robot-md` entry into `claude_desktop_config.json` on the right OS path. Restart Claude Desktop, get the same MCP surface. See [`integrations/claude-desktop/`](../integrations/claude-desktop/).
- **Claude Mobile** (iOS/Android): host `ROBOT.md` at a public HTTPS URL, paste the URL into Claude Mobile. `robot-md publish-discovery ROBOT.md --url <URL>` emits the `.well-known/robot-md.json` discovery doc. See [`integrations/claude-mobile/`](../integrations/claude-mobile/).
- **Superpowers-aware harness** (auto-invoke skill): `robot-md install-skill` drops the `using-robot-md` skill into `~/.claude/skills/` so Claude auto-invokes the flow on robot-related intent without the operator having to name the tooling.

When you outgrow single-session operation (fleet, hardware interlocks, reactive VLA control, EU AI Act audit), add [OpenCastor](https://github.com/craigm26/OpenCastor). Until then, the flow above is the whole stack.

---

## See also

- [README — On your machine (terminal)](../README.md#-option-a--on-your-machine-terminal-recommended) — the equivalent shell flow.
- [Claude Desktop integration](../integrations/claude-desktop/README.md) — macOS/Windows app install path.
- [Claude Mobile integration](../integrations/claude-mobile/README.md) — iOS/Android URL-fetch pattern.
- [robot-md-mcp](https://github.com/RobotRegistryFoundation/robot-md-mcp) — the MCP server Claude Code uses to read the manifest.
- [Bob (reference robot)](../examples/bob.ROBOT.md) — a fully populated ROBOT.md with real RRN + kinematics.
- [spec/robot-md-v1.md](../spec/robot-md-v1.md) — authoritative file format spec.
