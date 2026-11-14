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
2. Give you `robot-md init my-bob --preset so-arm101 --register --manufacturer acme --contact-email me@acme.com` to run in a terminal at the robot. `init` opens every serial port to look for servos and opens the camera, and at a terminal it can move each joint to calibrate it, so it is yours to run, not Claude's. (`ROBOT_MD_SKIP_BUS_PROBE=1` skips only the servo probe; the camera is still opened, so it doesn't make `init` safe to hand to Claude.)
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

Claude: I'll install the CLI, then hand you the init command: it
        opens the robot's serial ports and camera, so you run it
        at the robot.

        [runs: pip install robot-md]
        ✓ robot-md installed

        Run this in a terminal at the robot:
          robot-md init my-bob --preset so-arm101 --register \
              --manufacturer acme --contact-email me@acme.com

You: [runs it] done.

Claude: [reads ROBOT.md]
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
        arm.pick, arm.place, arm.reach, arm.home, status.report.
        Max payload 0.5 kg. Software E-stop at 100 ms. The manifest
        gates `destructive` and `system` with require_auth: true,
        so robot-md's MCP server refuses every motion until a
        person's confirmation can reach it from outside this chat.
        I can read the robot's state.
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

Claude gives you `robot-md init my-bob --wizard` to run at the robot (it opens the serial ports, like any `init`), helps you answer its prompts, and validates the draft. Review it, then ask:

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

Claude gives you `robot-md calibrate --zero ROBOT.md` to run in a terminal at the robot: calibration opens the servo port directly, so it is yours to run, not Claude's. You pose the arm, press Enter, and the CLI records the encoder readings into the manifest; Claude can then read them back. `--extrinsic` (formerly `--hand-eye`) moves the arm through calibration poses, so the same applies with more reason: you run it, with a hand on the power switch.

---

### After init on a TTY with the arm plugged in

Once `robot-md init` finishes, install the gateway on the robot. Motion goes only through it, and without it the MCP motion tools refuse. You run this yourself: it installs a service that takes the robot's servo port.

```bash
robot-md install-gateway
```

Then, still as the person at the robot:

1. **Give the MCP server its token.** `install-gateway` keeps `/etc/robot-md-gateway/bearers.yaml` readable by the gateway only, so the MCP server can't read it. Set `ROBOT_MD_GATEWAY_BEARER` to the actuate token in the MCP server's environment, or `ROBOT_MD_BEARERS_FILE` to a file of your own holding only that entry.
2. **If your gateway boots held, arm it.** robot-md-gateway with #35 or later starts held and moves nothing until you send its heartbeat from your own device with the supervisor token (never from the robot or the machine Claude runs on), then `POST /v1/safety/clear` with your commission token. Where the gateway requires signed envelopes, as `install-gateway` sets it, that clear must carry a signed `ESTOP_CLEAR` body, and the token alone gets a 403. robot-md-gateway's own `heartbeat` and `clear` commands send both, the clear signed with a key you pass; they are in robot-md-gateway#36, which isn't merged yet. A gateway without #35 (0.5.0a9 and earlier) doesn't boot held and serves neither `/v1/safety/heartbeat` nor `/v1/safety/clear`, so there is nothing to arm. The MCP server never sends heartbeats.
3. **Know what your gateway's stop does.** With #35 or later, a declared stop passes every gate, and the gateway stops the arm when the heartbeats stop. Without #35, the MCP stop has to pass every gate a motion does, so a manifest-pin mismatch, a missing signing key or a failed key lookup refuses it, and there is no heartbeat safe-stop; the MCP server warns when it finds such a gateway. On either, your hardware stop is the one that depends on no software.

Then, with you at the arm and a hand on a hardware stop (the power switch or plug):

```bash
cd ~/your-robot-dir
claude
```

Inside Claude Code, say:

```
Pick the red lego and put it in the bowl.
```

**On a manifest made from the so-arm101 preset, Claude moves nothing.** The preset gates `destructive` and `system` with `require_auth: true`. A gate that needs a person covers every motion, and that person's confirmation has to reach the gateway from outside the conversation, which robot-md can't take yet. So `execute_capability` refuses every motion, dry runs included (`hitl_gate`), and Claude says so and offers you the steps to run yourself. Reads such as `status.report` still work. If the bounded-embodiment plugin is installed, Claude calls no motion tool on real hardware at all.

On a manifest with no gate that needs a person:

Claude reads `CLAUDE.md`, asks you to confirm you are at the machine with a hand on the hardware stop, and calls `mcp__robot-md-<your_robot_name>__execute_capability(arm.pick, dry_run=true)` to show you the exact envelope it would send to robot-md-gateway; a dry run sends nothing. When you ask for the real thing, the same call without `dry_run` goes to the gateway, which checks it against the credential's tier, its tool allowlist and the actuator's limits, and runs it or refuses it. Claude reports the gateway's answer as given.

Your "yes" in the chat is not what allows the motion: the gateway decides. `status: ok` means the gateway ran the call; Claude checks `reached` before treating a move as done, since a stop that interrupts a move still gets `ok` with `reached: false`.

**Stopping and resuming.** Claude calls `estop` when you ask it to stop; if the stop isn't confirmed within 2 s, it tells you to use the hardware stop. Claude never clears a stop: `estop_clear` always refuses. You clear it yourself: if the gateway tripped (robot-md-gateway with #35 or later; it answers `deny: safety_state`), clear the gateway first, as in step 2, signed where it requires signatures; then clear the arm's latch with `robot-md invoke /etc/robot-md-gateway/ROBOT.md --tool arm.estop.clear --scope COMMISSION --bearer <your commission token>`. Name the ROBOT.md copy the gateway pins: with your own copy's path the gateway refuses the clear (`manifest_pin`). Then reconnect the MCP server (`/mcp` → robot-md → Reconnect): it keeps its own latch until it restarts.

**Behind a `commission` gate.** If the pinned ROBOT.md gates `commission` (`require_auth: true`, which no preset does), the gateway refuses that clear too (`hitl_required`), and robot-md can't attach a person's approval to it. There are two ways back, and each costs something:

- **Take the gate out.** Remove the `commission` gate from `/etc/robot-md-gateway/ROBOT.md`, sign the file again, and send the clear; the gateway reads the gates again at the next request. Later clears go ungated too, until you put the gate back. The gateway refuses every request on a manifest whose signature doesn't match (`manifest_provenance`), on 0.5.0a9 the stop included, and robot-md has no command that signs a ROBOT.md. `robot-md install-gateway` doesn't re-pin a running gateway: it stops at "already installed and active".
- **Restart the gateway.** The arm's latch lives in the gateway's process and goes with it, so nothing records who resumed the arm. A gateway with #35 then boots held, and its own clear (step 2) is recorded; on 0.5.0a9 the arm can be moved again as soon as the gateway is up.

Don't relabel the clear's scope (`--scope SAFETY`, say) to get it past the gate: that defeats the gate your manifest declares. Either way, reconnect the MCP server afterwards.

### For scripted / CI callers

```bash
robot-md init bob --preset so-arm101 --non-interactive
```

Manifest-only: no prompts, no MCP or skill install, no calibration. It still scans the machine first: it opens each serial port to look for servos (`ROBOT_MD_SKIP_BUS_PROBE=1` skips that) and opens any OAK-D camera, so on the robot it is the person's to run.

---

## What Claude is allowed to do

Claude Code honors your permission mode. In the default *accept edits* mode, it will:

- ✅ Run `pip install robot-md`, `npx robot-md-mcp`, `claude mcp add` — installation + wiring.
- ✅ Run `robot-md register / validate / render`, and `robot-md doctor --path ROBOT.md --hardware off` — manifest lifecycle and diagnosis.
- ✅ Call the MCP motion tools, which send to robot-md-gateway, once you have confirmed you are at the machine with a hardware stop in reach, on a manifest with no gate that needs a person, and only when the bounded-embodiment plugin isn't installed.
- ✋ **Leaves to you:** anything that opens the servo port or the camera, or starts a service that drives the robot (`robot-md init`, `robot-md calibrate`, `robot-md pose teach`, `robot-md doctor` without `--hardware off`, `robot-md install-gateway`), clearing a stop, and starting a test run (`robot-md trial`, Bounded Embodiment runs).
- ✅ Read and edit files under your project directory.
- ⚠ **Ask before:** destructive operations (deleting registrations, `robot-md unregister <rrn>`), writing files outside the project, publishing to external registries with non-default endpoints.

If you want stricter control, start Claude Code in plan mode (`claude --permission-mode plan`) — it will present the plan first and wait for your approval before running anything.

---

## What if something goes wrong?

Ask Claude directly:

```
Something broke — run robot-md doctor and tell me what's wrong.
```

Claude runs `robot-md doctor --path ROBOT.md --hardware off` and reports (RRF/rcan.dev reachable, schema valid, keystore integrity, claude CLI present, declared driver devices present). `--hardware off` keeps it off the servo port: without it, `doctor --path` opens the port and reads every servo whenever one is plugged in, so a hardware check (`--hardware on`) is yours to run.

---

## What happens next

Your robot now has:

- ✅ A validated `ROBOT.md` at the project root.
- ✅ A `CLAUDE.md` sibling (generated by `init`) — the intent→action table Claude reads at session start.
- ✅ A public identity: `RRN-NNNNNNNNNNNN`, resolvable at `https://rcan.dev/r/<rrn>`.
- ✅ A live MCP server in this Claude Code session — six `robot-md://` resources, three tools (`validate`, `render`, `doctor_summary`), four slash commands (`/brief-me`, `/check-safety`, `/explain-capability`, `/manifest-status`).

From here, Claude Code plans, and robot-md-gateway decides every motion it proposes. A manifest gate that needs a person stops MCP motion altogether until robot-md can take that person's confirmation from outside the chat.

**Try these next:**

- `/brief-me` — get a concise briefing on the robot.
- `/check-safety action="pick up the red cup"` — before issuing any motion, cross-check the action against declared HITL gates.
- Ask Claude: *"Run `robot-md doctor --path ROBOT.md --hardware off` and tell me what's wrong."* — diagnostic across install, manifest, network, drivers, keystore, without opening the servo port.

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
