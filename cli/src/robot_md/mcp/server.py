"""robot-md MCP server — stdio, registers render / validate / estop.

More tools (`execute_capability`, `execute_task`) are registered in later tasks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import Context

from robot_md.mcp.context import McpContext, load_context
from robot_md.mcp.tools.doctor_summary import doctor_summary_tool
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool
from robot_md.mcp.tools.render import render_tool
from robot_md.mcp.tools.validate import validate_tool


def find_manifest_via_cwd_walk(start: Path) -> Path | None:
    """Walk up from `start` looking for ROBOT.md. Returns the path or None.

    Stops at the filesystem root. Used by `robot-md mcp` (no positional arg)
    and by the plugin's .mcp.json that spawns `robot-md mcp` from the
    project directory at session start.
    """
    current = start.resolve()
    while True:
        candidate = current / "ROBOT.md"
        if candidate.is_file():
            return candidate
        if current.parent == current:  # filesystem root
            return None
        current = current.parent


def build_server(ctx: McpContext):
    """Build a FastMCP server with the render/validate/estop tools bound to ctx."""
    from contextlib import asynccontextmanager

    from mcp.server.fastmcp import FastMCP

    # SP-AN: opportunistic active-session capture + lifespan-managed
    # subscribers. v1 single-session limitation documented in
    # cli/docs/hotplug-roadmap.md and the 2026-04-30 spike findings.
    _an_state: dict = {"active_session": None}

    @asynccontextmanager
    async def _lifespan(_server):
        from robot_md.hotplug.queue import _DEFAULT_PATH as _HOTPLUG_QUEUE_PATH
        from robot_md.mcp.resource_subscribers import (
            FilePollFallback,
            HotplugResourceSubscriber,
            make_an_emit,
        )
        from robot_md.mcp.resources.hotplug_pending import URI as _U

        emit = make_an_emit(_an_state, _U)
        sub = HotplugResourceSubscriber(on_change=emit)
        fallback = FilePollFallback(
            queue_path=_HOTPLUG_QUEUE_PATH, on_change=emit, interval=2.0,
        )
        await sub.start()
        await fallback.start()
        try:
            yield {}
        finally:
            await sub.stop()
            await fallback.stop()

    server = FastMCP("robot-md", lifespan=_lifespan)

    @server.tool()
    def render() -> str:
        """Strip prose and return the frontmatter as canonical YAML."""
        return render_tool(ctx)

    @server.tool()
    def validate() -> dict:
        """Validate the served ROBOT.md against the v1 schema and body rules."""
        return validate_tool(ctx)

    @server.tool()
    def estop() -> dict:
        """Set the software E-stop for this server session."""
        return estop_tool(ctx)

    @server.tool()
    def estop_clear(confirm_token: str | None = None) -> dict:
        """Clear the software E-stop. Gated by the `system` HITL scope by default."""
        return estop_clear_tool(ctx, confirm_token=confirm_token)

    @server.tool()
    def execute_capability(
        capability: str,
        args: dict | None = None,
        dry_run: bool = False,
        confirm_token: str | None = None,
    ) -> dict:
        """Execute a declared capability against the resolved backend."""
        from robot_md.mcp.tools.execute_capability import execute_capability_tool

        return execute_capability_tool(
            ctx,
            capability=capability,
            args=dict(args or {}),
            dry_run=dry_run,
            confirm_token=confirm_token,
        )

    @server.tool()
    def execute_task(
        prompt: str,
        context: dict | None = None,
        dry_run: bool = False,
        confirm_token: str | None = None,
    ) -> dict:
        """Decompose a natural-language task into capability steps and run them."""
        from robot_md.mcp.tools.execute_task import execute_task_tool

        return execute_task_tool(
            ctx,
            prompt=prompt,
            context=context,
            dry_run=dry_run,
            confirm_token=confirm_token,
        )

    @server.tool()
    def vision_find(descriptor_id: str) -> dict:
        """Detect one declared object descriptor. Returns camera-frame XYZ (mm)."""
        from robot_md.mcp.tools.vision_find import vision_find_tool

        return vision_find_tool(ctx, descriptor_id=descriptor_id)

    @server.tool()
    def record_skill(
        skill_id: str,
        status: str = "ok",
        validated: list[str] | None = None,
        blocked_by: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        """Append/upsert a learned_skills[] entry on the served ROBOT.md."""
        from robot_md.mcp.tools.record_skill import record_skill_tool

        return record_skill_tool(
            ctx,
            skill_id=skill_id,
            status=status,
            validated=validated,
            blocked_by=blocked_by,
            notes=notes,
        )

    @server.tool()
    async def discover(steps: list[dict], mcp_ctx: Context | None = None) -> dict:
        """Run the declarative discovery pipeline.

        Supported steps: capture, detect, probe_direction. See
        docs/superpowers/specs/2026-04-19-claude-triad-gap-analysis.md §8.

        FastMCP injects `mcp_ctx` for progress notifications; direct callers
        may omit it and `report_progress` will be skipped.
        """
        from robot_md.mcp.tools.discover import discover_tool

        return await discover_tool(ctx, steps=steps, mcp_ctx=mcp_ctx)

    @server.tool()
    def doctor_summary() -> dict:
        """Read-only manifest-only sanity check.

        Returns schema status, identity fields, driver summary, HITL gates,
        E-stop config, and registration status. Cheaper and safer than
        `robot-md doctor` (which also probes network + drivers). Use when
        the operator asks "is everything OK", "quick-check", or "what's the
        state of the manifest". For live hardware diagnostics, tell the
        operator to run `robot-md doctor` from the shell.
        """
        return doctor_summary_tool(ctx)

    # ── SP6 spatial-intelligence eval tools ──────────────────────────────────
    # 9 tools wrapping cli/src/robot_md/spatial_eval/* core logic. Each public
    # shim only exposes JSON-serializable args; the underlying *_tool functions
    # have private `_*` injection kwargs for tests, kept off the FastMCP surface.

    @server.tool()
    def spatial_eval_dry_run() -> dict:
        """Preflight: spatial-eval section, ANTHROPIC_API_KEY, judge camera."""
        from robot_md.mcp.tools.spatial_eval.dry_run import dry_run_tool

        return dry_run_tool(ctx)

    @server.tool()
    def spatial_eval_init(units: list[str]) -> dict:
        """Scaffold the spatial-eval: section into the served ROBOT.md."""
        from robot_md.mcp.tools.spatial_eval.init import init_tool

        return init_tool(ctx, units=units)

    @server.tool()
    def spatial_eval_kit() -> dict:
        """Return the v1 fixture-kit BOM and grid-mat path."""
        from robot_md.mcp.tools.spatial_eval.kit import kit_tool

        return kit_tool(ctx)

    @server.tool()
    def spatial_eval_run_probe(units: list[str] | None = None, baseline_only: bool = False) -> dict:
        """Run the probe track. Returns Score JSON probe section."""
        from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool

        return run_probe_tool(ctx, units=units, baseline_only=baseline_only)

    @server.tool()
    def spatial_eval_run_execute(
        units: list[str] | None = None,
        trials_per_unit: int = 10,
        run_dir: str | None = None,
    ) -> dict:
        """Run the execute track on hardware. Returns Score JSON + run_dir."""
        from pathlib import Path as _Path

        from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool

        return run_execute_tool(
            ctx,
            units=units,
            trials_per_unit=trials_per_unit,
            run_dir=_Path(run_dir) if run_dir else None,
        )

    @server.tool()
    def spatial_eval_run_full(
        units: list[str] | None = None,
        trials_per_unit: int = 10,
        run_dir: str | None = None,
    ) -> dict:
        """Run both tracks (probe + execute) and merge results."""
        from pathlib import Path as _Path

        from robot_md.mcp.tools.spatial_eval.run_full import run_full_tool

        return run_full_tool(
            ctx,
            units=units,
            trials_per_unit=trials_per_unit,
            run_dir=_Path(run_dir) if run_dir else None,
        )

    @server.tool()
    def spatial_eval_replay(run_dir: str) -> dict:
        """Recompute Score JSON from an existing evidence packet without re-running."""
        from pathlib import Path as _Path

        from robot_md.mcp.tools.spatial_eval.replay import replay_tool

        return replay_tool(ctx, run_dir=_Path(run_dir))

    @server.tool()
    def spatial_eval_verify(score_json: str) -> dict:
        """Verify a Score JSON's RCAN ML-DSA signature.

        Loads the signing keypair from ~/.robot-md/keys/<rrn>.signing.json
        for the score's `rrn` and verifies `rcan_signature` against the
        canonical bytes of the score with `rcan_signature` cleared. Returns
        `attestation: self-attested` on success. Returns a clean
        keystore-miss error if the keypair isn't on disk (the robot was
        registered elsewhere or the keystore was cleaned up). The signer
        side (run_execute_tool emitting an `rcan_signature` on Score.json)
        is a separate follow-up.
        """
        from robot_md.mcp.tools.spatial_eval.verify import verify_tool

        return verify_tool(ctx, score_json=score_json)

    @server.tool()
    def spatial_eval_submit_to_rrf(run_dir: str) -> dict:
        """Submit signed evidence to RRF §27 (Phase 1 stub for now)."""
        from robot_md.mcp.tools.spatial_eval.submit_to_rrf import submit_to_rrf_tool

        return submit_to_rrf_tool(ctx, run_dir=run_dir)

    @server.tool()
    def hotplug_review() -> dict:
        """Return all currently-pending (unresolved) hot-plug events for operator review."""
        from robot_md.mcp.tools.hotplug_review import hotplug_review_tool

        return hotplug_review_tool()

    @server.tool()
    def hotplug_confirm(
        event_id: str, decision: str, choice_index: int | None = None,
    ) -> dict:
        """Bind or reject a pending hot-plug event. decision is 'bind' or 'reject'."""
        from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool

        return hotplug_confirm_tool(
            event_id=event_id, decision=decision, choice_index=choice_index,
        )

    from robot_md.mcp.resources import _sanitize_robot_name

    robot_name = _sanitize_robot_name(ctx.spec.metadata.robot_name if ctx.spec else None)

    @server.resource(f"robot-md://{robot_name}/learned_skills", mime_type="application/json")
    def _resource_learned_skills() -> str:
        import json

        from robot_md.mcp.resources import learned_skills as _ls

        return json.dumps(_ls(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/calibration_status", mime_type="application/json")
    def _resource_calibration_status() -> str:
        import json

        from robot_md.mcp.resources import calibration_status as _cs

        return json.dumps(_cs(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/poses", mime_type="application/json")
    def _resource_poses() -> str:
        import json

        from robot_md.mcp.resources import poses as _poses

        return json.dumps(_poses(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/recent_invocations", mime_type="application/json")
    def _resource_recent_invocations() -> str:
        import json

        from robot_md.mcp.resources import recent_invocations as _ri

        return json.dumps(_ri(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/recent_errors", mime_type="application/json")
    def _resource_recent_errors() -> str:
        import json

        from robot_md.mcp.resources import recent_errors as _re

        return json.dumps(_re(ctx), indent=2)

    # SP-AN: hot-plug pending events. Each read captures the active
    # session so the lifespan-managed subscriber can target it for
    # notifications/resources/updated. v1 single-session limitation; see
    # docs/superpowers/specs/2026-04-30-span-fastmcp-subscribe-spike.md.
    from robot_md.mcp.resources.hotplug_pending import URI as _HOTPLUG_PENDING_URI

    @server.resource(_HOTPLUG_PENDING_URI, mime_type="application/json")
    def _resource_hotplug_pending() -> str:
        import json

        from robot_md.mcp.resources.hotplug_pending import build_pending_payload

        try:
            ctx_ = server.get_context()
            if ctx_ is not None:
                _an_state["active_session"] = ctx_.session
        except (LookupError, RuntimeError, AttributeError):
            pass

        return json.dumps(build_pending_payload(), indent=2)

    # ── Prompts (slash commands in Claude Desktop/Code) ──────────────────────
    # Raw robot name for human-readable prompt text (trimmed, not URI-sanitized).
    _raw_robot_name = (ctx.spec.metadata.robot_name if ctx.spec else None) or robot_name

    @server.prompt(
        name="brief-me",
        title=f"Brief me on {_raw_robot_name}",
        description=(
            f"Produce a concise operator briefing on {_raw_robot_name}: identity, "
            "capabilities, safety gates, current registration status. Read the context "
            "resource; do not guess."
        ),
    )
    def _prompt_brief_me() -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    f"Read the resource `robot-md://{robot_name}/context` (or its narrower "
                    f"cousins `/identity`, `/capabilities`, `/safety`) and produce a short "
                    f"operator briefing on {_raw_robot_name}:\n\n"
                    "1. **Identity** — one line (name, type, DoF, manufacturer/model/"
                    "version, RRN).\n"
                    "2. **Capabilities** — bullet list of declared actions.\n"
                    "3. **Safety posture** — declared HITL gates, E-stop config, payload limits.\n"
                    "4. **Registration** — registered on rcan.dev? If so, include the "
                    "public resolver URL.\n\n"
                    "Keep it to under 200 words. Do not invent capabilities or limits "
                    "not in the manifest."
                ),
            }
        ]

    @server.prompt(
        name="check-safety",
        title="Is this action safe?",
        description=(
            f"Check a proposed action against {_raw_robot_name}'s declared HITL gates "
            "and safety envelope. Use before issuing any physical motion."
        ),
    )
    def _prompt_check_safety(action: str) -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    f"The operator wants {_raw_robot_name} to do: **{action}**\n\n"
                    f"Read `robot-md://{robot_name}/safety` and determine:\n\n"
                    "1. Does this action's scope match a declared `hitl_gates[]` entry with "
                    "`require_auth: true`? If yes, name the gate and tell the operator you need "
                    "explicit authorization before proceeding.\n"
                    "2. Does the action stay within `payload_kg`, `max_joint_velocity_dps`, and "
                    "`workspace_bounds_m` (if declared)?\n"
                    "3. Is `estop.software` available? Confirm the driver command path "
                    "to trigger it.\n"
                    "4. If no matching gate exists AND the action is potentially harmful "
                    "(unknown objects, "
                    "high velocity, collision risk, workspace-boundary-approaching): "
                    "**surface the gap to "
                    "the operator** — say the manifest doesn't declare a gate for this "
                    "scope and ask "
                    "whether to add one or to authorize this specific action.\n\n"
                    'Reply with one of: "✓ safe to proceed", "⚠ authorization required — '
                    '<gate scope>", or "⚠ gate gap — <explanation>". Do not assume; only answer '
                    "from the declared manifest."
                ),
            }
        ]

    @server.prompt(
        name="explain-capability",
        title="Explain a capability",
        description=(
            f"Explain what one of {_raw_robot_name}'s declared capabilities does, "
            "which drivers it uses, and which safety gates apply."
        ),
    )
    def _prompt_explain_capability(capability: str) -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    f"The operator asked about the `{capability}` capability on "
                    f"{_raw_robot_name}.\n\n"
                    f"1. Read `robot-md://{robot_name}/capabilities`. Confirm the capability "
                    "is actually declared. If not, tell the operator the capability is NOT "
                    "declared and list what IS declared.\n"
                    f"2. If declared, read `robot-md://{robot_name}/frontmatter` and `/body` "
                    "to find which drivers + kinematics this capability uses and any "
                    "operator-authored prose about it.\n"
                    f"3. Read `robot-md://{robot_name}/safety` and identify any `hitl_gates[]` "
                    "whose scope would apply when this capability is invoked.\n"
                    "4. Produce an answer with: what the capability does, hardware path, "
                    "safety gates that apply. Keep to under 150 words."
                ),
            }
        ]

    @server.prompt(
        name="manifest-status",
        title="Quick status check on the ROBOT.md",
        description=(
            f"Run the doctor_summary tool and translate the JSON into a "
            f"human-readable health summary for {_raw_robot_name}."
        ),
    )
    def _prompt_manifest_status() -> list[dict]:
        return [
            {
                "role": "user",
                "content": (
                    f"Call the `doctor_summary` tool and translate its JSON output into a "
                    f"short status report for {_raw_robot_name}:\n\n"
                    "- ✓ Schema valid? (if not, list the errors)\n"
                    "- ✓ Registered on rcan.dev? (if so, note the RRN)\n"
                    "- Drivers: per-driver port/host summary\n"
                    "- HITL gates: count + scopes\n"
                    "- E-stop: software/hardware/response time\n"
                    "- Any obvious gaps or things the operator should know\n\n"
                    "Keep it under 150 words. This is a quick-check, not a full diagnosis "
                    "— for that, suggest the operator run `robot-md doctor` from the shell."
                ),
            }
        ]

    return server


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: robot-md-mcp <ROBOT.md>", file=sys.stderr)
        return 2
    manifest = Path(sys.argv[1])
    try:
        ctx = load_context(manifest)
    except Exception as e:
        print(f"robot-md-mcp: fatal: {e}", file=sys.stderr)
        return 1
    server = build_server(ctx)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
