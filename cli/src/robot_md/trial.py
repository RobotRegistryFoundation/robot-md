"""robot-md trial: capture pick-and-place trial evidence for cert minting.

State directory layout (per trial):
    ~/.robot-md/trials/<trial_id>/
        start.json
        iter_<N>.json
        evidence.json     (written by `trial finalize`)
        frames/iter_<N>_{pre,post}_{rgb,depth}.png

Cold-install wall-clock anchor:
    ~/.robot-md-cold-install-start.txt  (operator-written before cold install)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import secrets
import urllib.request
import uuid

import typer

trial_app = typer.Typer(help="Capture pick-and-place trial evidence for cert minting.")


@trial_app.callback()
def _trial_callback() -> None:
    """Capture pick-and-place trial evidence for cert minting."""


TRIALS_DIR = pathlib.Path.home() / ".robot-md" / "trials"
COLD_INSTALL_START_FILE = pathlib.Path.home() / ".robot-md-cold-install-start.txt"


def _utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trial_dir(trial_id: str) -> pathlib.Path:
    return TRIALS_DIR / trial_id


def _read_cold_install_start() -> str | None:
    if not COLD_INSTALL_START_FILE.exists():
        return None
    raw = COLD_INSTALL_START_FILE.read_text().strip()
    try:
        dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return raw


@trial_app.command("start")
def start_cmd(
    property_: str = typer.Option(
        ...,
        "--property",
        help="Cert property name (e.g., bob.local/PICK-PLACE-10)",
    ),
) -> None:
    """Begin a new trial. Writes start.json with timestamps + property."""
    trial_id = "trial_" + secrets.token_hex(3)
    d = _trial_dir(trial_id)
    d.mkdir(parents=True, exist_ok=False)
    (d / "frames").mkdir()
    cold_install_start = _read_cold_install_start()
    anchor = "claude_code_first_command" if cold_install_start else "robot_md_trial_start_only"
    state = {
        "trial_id": trial_id,
        "property": property_,
        "started_at": _utcnow_iso(),
        "cold_install_start_marker": cold_install_start,
        "start_anchor": anchor,
        "iterations": [],
        "aborted_at": None,
    }
    (d / "start.json").write_text(json.dumps(state, indent=2) + "\n")
    typer.echo(f"Trial {property_} started at {state['started_at']}")
    if cold_install_start:
        typer.echo(
            f"  cold_install_start_marker: {cold_install_start}  (from {COLD_INSTALL_START_FILE})"
        )
    else:
        typer.echo(
            f"  ({COLD_INSTALL_START_FILE} not found"
            " — wall-clock anchor downgraded to post-install)"
        )
    missing_env = [
        v for v in ("ROBOT_MD_RURI", "ROBOT_MD_MANIFEST_PATH")
        if not os.environ.get(v)
    ]
    if missing_env:
        typer.echo(
            "  WARN: capture-pre / capture-post will fail with RuntimeError until you set "
            + ", ".join(missing_env)
            + " (required for the gateway envelope; see robot-md 1.10.1 release notes)."
        )
    typer.echo(f"Trial ID: {trial_id}")
    typer.echo("→ Run your Claude Code session now. After each iteration:")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --capture-pre")
    typer.echo("  → Claude does its thing →")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --capture-post-and-verdict")
    typer.echo("  → reset brick →")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --reset-confirmed")


def _next_iter_number(trial_dir: pathlib.Path) -> int:
    existing = sorted(trial_dir.glob("iter_*.json"))
    return len(existing) + 1


def _gateway_invoke(actuator: str, tool: str, args: dict) -> dict:
    """POST a full InvokeEnvelope to the gateway and return the parsed response.

    The receiver requires msg_id / type / ruri / scope / tool_name / tool_args /
    manifest_path. The first three live outside any single trial command and
    are read from env vars set once by the operator before `trial start`:

        ROBOT_MD_RURI           e.g. rcan://RRN-000000000002/skill
        ROBOT_MD_SCOPE          e.g. "read" (default) or "actuate"
        ROBOT_MD_MANIFEST_PATH  absolute path to ROBOT.md on this host

    `msg_id` is generated per request. The gateway must be configured with
    multi-actuator dispatch (robot-md-gateway >= 0.5.0a3) — `actuator_name`
    selects between the perception and motion actuators.

    Raises RuntimeError if any required env var is missing — fail loudly
    rather than send a 422-bound request.
    """
    ruri = os.environ.get("ROBOT_MD_RURI")
    if not ruri:
        raise RuntimeError(
            "ROBOT_MD_RURI is required by robot-md trial. "
            "Set it once before `robot-md trial start` (the rcan:// URI of "
            "this robot's RRN registration)."
        )
    manifest_path = os.environ.get("ROBOT_MD_MANIFEST_PATH")
    if not manifest_path:
        raise RuntimeError(
            "ROBOT_MD_MANIFEST_PATH is required by robot-md trial. "
            "Set it to the absolute path of the signed ROBOT.md the gateway "
            "should verify against (e.g., ~/.robot-md/ROBOT.md)."
        )
    scope = os.environ.get("ROBOT_MD_SCOPE", "read")

    url = os.environ.get("ROBOT_MD_GATEWAY_URL", "http://127.0.0.1:8080") + "/v1/invoke"
    bearer = os.environ.get("ROBOT_MD_GATEWAY_BEARER", "")
    envelope = {
        "msg_id": f"trial-{uuid.uuid4().hex[:12]}",
        "type": "rcan/v1/invoke",
        "ruri": ruri,
        "scope": scope,
        "tool_name": tool,
        "tool_args": args,
        "manifest_path": manifest_path,
        "actuator_name": actuator,
    }
    body = json.dumps(envelope).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


@trial_app.command("iteration")
def iteration_cmd(
    trial_id: str = typer.Option(..., "--trial", help="Trial ID from `robot-md trial start`"),
    capture_pre: bool = typer.Option(False, "--capture-pre"),
    capture_post: bool = typer.Option(False, "--capture-post-and-verdict"),
    reset_confirmed: bool = typer.Option(False, "--reset-confirmed"),
) -> None:
    """Capture pre/post state for one iteration of a trial."""
    d = _trial_dir(trial_id)
    if not d.exists():
        typer.echo(f"error: unknown trial: {trial_id}")
        raise typer.Exit(code=2)

    n = sum([capture_pre, capture_post, reset_confirmed])
    if n != 1:
        typer.echo(
            "error: pass exactly one of --capture-pre, --capture-post-and-verdict,"
            " --reset-confirmed"
        )
        raise typer.Exit(code=2)

    state = json.loads((d / "start.json").read_text())
    if state.get("aborted_at"):
        typer.echo(f"error: trial aborted at {state['aborted_at']}")
        raise typer.Exit(code=2)

    if capture_pre:
        _capture_pre(d)
        return
    if capture_post:
        _capture_post(d)
        return
    if reset_confirmed:
        _reset_confirmed(d)
        return


VERDICT_RULE = (
    "post.red_blob.centroid_px ∈ post.bowl_top.bbox_px AND "
    "|post.red_blob.centroid_depth_mm - post.bowl_top.centroid_depth_mm| <= 80"
)
DEPTH_DELTA_TOLERANCE_MM = 80


def _capture_pre(d: pathlib.Path) -> None:
    n = _next_iter_number(d)
    red = _gateway_invoke("oak-d", "perceive", {"query": "red_blob"})
    bowl = _gateway_invoke("oak-d", "perceive", {"query": "bowl_top"})
    state = _gateway_invoke("so-arm101", "read_state", {})
    iter_state = {
        "iteration": n,
        "started_at": _utcnow_iso(),
        "pre_state": {
            "joint_positions_rad": state.get("telemetry", {}).get("positions", {}),
            "perceive_red_blob": red.get("telemetry", {}),
            "perceive_bowl_top": bowl.get("telemetry", {}),
        },
    }
    (d / f"iter_{n}.json").write_text(json.dumps(iter_state, indent=2) + "\n")
    typer.echo(f"iteration {n}: pre-state captured at {iter_state['started_at']}")


def _capture_post(d: pathlib.Path) -> None:
    iters = sorted(d.glob("iter_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    if not iters:
        typer.echo("error: no iteration in progress; run --capture-pre first")
        raise typer.Exit(code=2)
    cur = iters[-1]
    state = json.loads(cur.read_text())
    if "post_state" in state:
        typer.echo(f"error: iteration {state['iteration']} already has post_state")
        raise typer.Exit(code=2)

    red = _gateway_invoke("oak-d", "perceive", {"query": "red_blob"})
    bowl = _gateway_invoke("oak-d", "perceive", {"query": "bowl_top"})
    joints = _gateway_invoke("so-arm101", "read_state", {})

    red_t = red.get("telemetry", {})
    bowl_t = bowl.get("telemetry", {})

    centroid_inside = False
    depth_delta = None
    pixel_distance = None
    if red_t.get("found") and bowl_t.get("found"):
        cu, cv = red_t["centroid_px"]
        u0, v0, u1, v1 = bowl_t["bbox_px"]
        centroid_inside = (u0 <= cu <= u1) and (v0 <= cv <= v1)
        depth_delta = abs(int(red_t["centroid_depth_mm"]) - int(bowl_t["centroid_depth_mm"]))
        bx, by = bowl_t["centroid_px"]
        pixel_distance = int(((cu - bx) ** 2 + (cv - by) ** 2) ** 0.5)
    depth_within = depth_delta is not None and depth_delta <= DEPTH_DELTA_TOLERANCE_MM
    red_in_bowl = bool(centroid_inside and depth_within)

    post_iso = _utcnow_iso()
    started = dt.datetime.strptime(state["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    ended = dt.datetime.strptime(post_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    duration_s = (ended - started).total_seconds()

    state["post_state"] = {
        "joint_positions_rad": joints.get("telemetry", {}).get("positions", {}),
        "perceive_red_blob": red_t,
        "perceive_bowl_top": bowl_t,
        "captured_at": post_iso,
    }
    state["duration_s"] = duration_s
    state["verdict"] = {
        "rule": VERDICT_RULE,
        "red_in_bowl": red_in_bowl,
        "centroid_inside_bbox": centroid_inside,
        "pixel_distance_to_bowl_centroid_px": pixel_distance,
        "depth_delta_mm": depth_delta,
        "pass": red_in_bowl,
    }
    cur.write_text(json.dumps(state, indent=2) + "\n")
    typer.echo(
        f"iteration {state['iteration']}: verdict={'PASS' if red_in_bowl else 'FAIL'}"
        f" duration={duration_s:.1f}s"
    )


def _reset_confirmed(d: pathlib.Path) -> None:
    iters = sorted(d.glob("iter_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    if not iters:
        typer.echo("error: no iteration to confirm reset for")
        raise typer.Exit(code=2)
    cur = iters[-1]
    state = json.loads(cur.read_text())
    state["operator_reset_confirmed_at"] = _utcnow_iso()
    cur.write_text(json.dumps(state, indent=2) + "\n")
    typer.echo(
        f"iteration {state['iteration']}: reset confirmed at {state['operator_reset_confirmed_at']}"
    )


WALL_CLOCK_TARGET_S = 600  # 10 minutes
EXPECTED_ITERATIONS = 10


def _parse_utc(s: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


@trial_app.command("finalize")
def finalize_cmd(
    trial_id: str = typer.Option(..., "--trial"),
) -> None:
    """Roll iter_*.json files into evidence.json with cold-install wall-clock verdict."""
    d = _trial_dir(trial_id)
    if not d.exists():
        typer.echo(f"error: unknown trial: {trial_id}")
        raise typer.Exit(code=2)
    start = json.loads((d / "start.json").read_text())
    iter_files = sorted(d.glob("iter_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    if len(iter_files) != EXPECTED_ITERATIONS:
        typer.echo(f"error: trial has {len(iter_files)} iterations, expected {EXPECTED_ITERATIONS}")
        raise typer.Exit(code=2)

    iters = [json.loads(p.read_text()) for p in iter_files]
    passed = sum(1 for it in iters if it.get("verdict", {}).get("pass"))
    trial_duration_s = sum(float(it.get("duration_s") or 0) for it in iters)

    cold_block: dict
    iter1 = iters[0]
    if iter1.get("verdict", {}).get("pass") and start.get("cold_install_start_marker"):
        start_marker = start["cold_install_start_marker"]
        end_marker = iter1["post_state"]["captured_at"]
        elapsed_s = (_parse_utc(end_marker) - _parse_utc(start_marker)).total_seconds()
        verdict = "PASS" if elapsed_s <= WALL_CLOCK_TARGET_S else "FAIL"
        cold_block = {
            "start_marker": start_marker,
            "start_anchor": start.get("start_anchor", "claude_code_first_command"),
            "end_marker": end_marker,
            "end_anchor": "iteration_1_pass",
            "elapsed_s": elapsed_s,
            "claim": f"≤ {WALL_CLOCK_TARGET_S} s (10 min)",
            "verdict": verdict,
        }
    else:
        cold_block = {
            "start_marker": start.get("cold_install_start_marker"),
            "start_anchor": start.get("start_anchor", "robot_md_trial_start_only"),
            "end_marker": None,
            "end_anchor": "iteration_1_pass",
            "elapsed_s": None,
            "claim": f"≤ {WALL_CLOCK_TARGET_S} s (10 min)",
            "verdict": "N/A",
        }

    evidence = {
        "property": start["property"],
        "rig": "bob-rig-2026",
        "rrn": "RRN-000000000002",
        "actuators": [
            {"name": "so-arm101", "rpn": "RPN-000000000002"},
            {"name": "oak-d", "rpn": "RPN-000000000003"},
        ],
        "captured_at": _utcnow_iso(),
        "trial_duration_s": trial_duration_s,
        "cold_install_wallclock": cold_block,
        "total": EXPECTED_ITERATIONS,
        "passed": passed,
        "iterations": iters,
        "scope_disclaimers": [
            "Per-motion HiTL claim NOT made; envelopes batch-signed by bob-operator-2026.",
            "Verification uses hardcoded HSV+depth thresholds;"
            " not robust to non-standard lighting.",
            "Camera mount: bird's-eye, ~30cm above table, pointing down.",
            "Claude reasoning quality affects trial duration; per-iteration soft timeout is 30s.",
            "Wall-clock anchor is operator-tagged; honor system.",
        ],
    }
    (d / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    typer.echo(
        f"Trial {trial_id} finalized."
        f" {passed}/{EXPECTED_ITERATIONS} passed."
        f" Total duration: {trial_duration_s:.0f}s."
    )
    typer.echo(f"Evidence at: {d / 'evidence.json'}")


@trial_app.command("abort")
def abort_cmd(
    trial_id: str = typer.Option(..., "--trial"),
) -> None:
    """Abort a trial, preventing further iterations."""
    d = _trial_dir(trial_id)
    if not d.exists():
        typer.echo(f"error: unknown trial: {trial_id}")
        raise typer.Exit(code=2)
    state = json.loads((d / "start.json").read_text())
    state["aborted_at"] = _utcnow_iso()
    (d / "start.json").write_text(json.dumps(state, indent=2) + "\n")
    typer.echo(f"trial {trial_id} aborted at {state['aborted_at']}")
