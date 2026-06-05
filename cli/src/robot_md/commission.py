"""robot-md commission (A1) — the reality-check commissioning loop.

Drives each joint through the gateway with `commission_probe` (incremental-step,
abort-on-stall), classifies the result, and (with --write) persists the discovered
endpoints into ROBOT.md + re-signs/deploys so the actuator's rad↔tick map becomes
hardware-true. This closes the original gripper bug (manifest "close" wider than "open")
at its source. Reporting reuses doctor's CheckResult(bucket="commission").

Hardware truth (proven live on Bob 2026-06-05):
  * commission_probe does NOT restore the joint after a stall — the caller MUST restore
    each joint after probing it (here: a gateway raw_tick_move back to start_tick).
  * The gripper's empty-jaw stall (~1455) is `close_steps_empty`, NOT `close_steps`
    (the grasp-stall tick on a held object, ~1200) — which an empty commission must
    PRESERVE, never overwrite.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from robot_md.doctor import CheckResult
from robot_md.invoke import (
    gateway_invoke,  # seam: tests monkeypatch robot_md.commission.gateway_invoke
)

_TICKS_PER_RAD = 4096.0 / (2.0 * math.pi)  # ≈ 651.9; matches so-arm101 config default

# Shipped per-joint rad bounds the rad↔tick RESOLVER pairs with min_steps/max_steps.
# MUST MATCH so-arm101 config.JOINTS min_rad/max_rad — the recorded ticks are meaningful
# only relative to these rad endpoints. The gripper is handled via solver.gripper ticks.
_JOINT_RAD_BOUNDS: dict[str, tuple[float, float]] = {
    "shoulder_pan": (-2.0, 2.0),
    "shoulder_lift": (-1.5, 1.5),
    "elbow_flex": (-1.8, 1.8),
    "wrist_flex": (-1.5, 1.5),
    "wrist_roll": (-2.5, 2.5),
}

ACTUATOR = "so-arm101"
COMMISSION_DIR = Path.home() / ".robot-md" / "commission"


def classify_probe(joint_id: str, result: dict) -> CheckResult:
    """Classify one `commission_probe` result into a CheckResult(bucket="commission").

    `result` carries the actuator's raw facts:
    {start_tick, commanded_tick, present_tick, moved, reached, aborted_on_stall}.

      * not moved        → FAIL — commanded but the joint never advanced (wiring / wrong
                           motor_id / torque off). Nothing was learned about its travel.
      * reached          → PASS — eased to the target with no stall (travel is at least
                           this far in this direction).
      * moved, not reached (aborted_on_stall) → WARN — stalled before the target: a
                           mechanical limit, or for the gripper a real grasp/floor. The
                           present_tick is the *discovered endpoint* — surface it.
    """
    present = result.get("present_tick")
    name = f"commission {joint_id}"
    if not result.get("moved"):
        return CheckResult(
            name,
            "commission",
            "fail",
            f"commanded but did not move (present {present}) — check motor_id / wiring / torque",
        )
    if result.get("reached"):
        return CheckResult(
            name, "commission", "pass", f"reached target cleanly (present {present})"
        )
    return CheckResult(
        name,
        "commission",
        "warn",
        f"stalled at {present} before target — endpoint candidate (mechanical limit or grasp)",
    )


def probe_targets(fm: dict) -> list[dict]:
    """Per-joint probe plan from the manifest frontmatter.

    Each entry: {joint_id, motor_id, target_min, target_max, is_gripper}.
      * non-gripper: targets = round(zero_pose_steps + min_rad/max_rad·651.9) for the
        SHIPPED rad bounds (the resolver's endpoints), clamped to [0, 4095].
      * gripper: target_min = solver.gripper.close_steps, target_max = open_steps (ticks).
    Joints with no rad bounds and not the gripper, or missing zero_pose_steps, are skipped
    (the caller surfaces a WARN) rather than guessed.
    """
    physics = fm.get("physics") or {}
    gripper_solver = (physics.get("solver") or {}).get("gripper") or {}
    out: list[dict] = []
    for j in physics.get("kinematics") or []:
        jid = j.get("id")
        motor_id = j.get("servo_id")
        if jid is None or motor_id is None:
            continue
        if jid == "gripper":
            close_s, open_s = gripper_solver.get("close_steps"), gripper_solver.get("open_steps")
            if close_s is None or open_s is None:
                continue
            out.append({
                "joint_id": jid, "motor_id": motor_id,
                "target_min": int(close_s), "target_max": int(open_s), "is_gripper": True,
            })
            continue
        bounds = _JOINT_RAD_BOUNDS.get(jid)
        zero = j.get("zero_pose_steps")
        if bounds is None or zero is None:
            continue
        min_rad, max_rad = bounds
        tmin = max(0, min(4095, round(zero + min_rad * _TICKS_PER_RAD)))
        tmax = max(0, min(4095, round(zero + max_rad * _TICKS_PER_RAD)))
        out.append({
            "joint_id": jid, "motor_id": motor_id,
            "target_min": tmin, "target_max": tmax, "is_gripper": False,
        })
    return out


def _probe(motor_id: int, joint_id: str, direction: int, target_ticks: int) -> dict:
    """One gateway-mediated commission_probe; returns its telemetry dict."""
    resp = gateway_invoke(
        ACTUATOR,
        "commission_probe",
        {"joint_id": joint_id, "motor_id": motor_id, "direction": direction,
         "target_ticks": int(target_ticks)},
        scope="COMMISSION",
    )
    return resp["telemetry"]


def _restore(motor_id: int, start_tick: int) -> None:
    """Gateway-mediated raw_tick_move back to start — commission_probe leaves the joint
    at the stall, so this is MANDATORY after every probe."""
    gateway_invoke(
        ACTUATOR, "raw_tick_move", {"motor_id": motor_id, "ticks": int(start_tick)},
        scope="COMMISSION",
    )


def probe_joint(plan: dict) -> dict:
    """Probe one joint toward min and max, restoring to start after EACH probe.

    Returns {joint_id, is_gripper, checks: [CheckResult,...],
             min_present, max_present} where *_present are the discovered tick endpoints.
    Restore runs in `finally` so a throwing probe still relieves the joint.
    """
    jid, motor_id = plan["joint_id"], plan["motor_id"]
    start: int | None = None
    checks: list[CheckResult] = []
    min_present = max_present = None
    try:
        pmin = _probe(motor_id, jid, -1, plan["target_min"])
        start = pmin["start_tick"]
        min_present = pmin["present_tick"]
        checks.append(classify_probe(f"{jid}→min", pmin))
        _restore(motor_id, start)
        pmax = _probe(motor_id, jid, +1, plan["target_max"])
        max_present = pmax["present_tick"]
        checks.append(classify_probe(f"{jid}→max", pmax))
    finally:
        if start is not None:
            _restore(motor_id, start)
    return {
        "joint_id": jid, "is_gripper": plan["is_gripper"], "checks": checks,
        "min_present": min_present, "max_present": max_present,
    }


def write_commissioned_to_manifest(
    manifest_path: str | Path, joint_endpoints: dict, gripper: dict
) -> int:
    """Ruamel write-back (comment/body-preserving — mirrors calibrate.write_zero_pose_to_manifest).

    joint_endpoints: {joint_id: {"min_steps": int, "max_steps": int}} — ALL probed joints,
        including the gripper kinematics entry (so doctor's "all joints commissioned" fires).
    gripper: {"open_steps", "close_steps", "close_steps_empty"} for physics.solver.gripper —
        the caller passes the EXISTING close_steps unchanged (empty commission can't measure it).
    Returns the number of kinematics joints updated.
    """
    try:
        from ruamel.yaml import YAML
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "`robot-md commission --write` needs ruamel.yaml. Install: pip install ruamel.yaml"
        ) from e

    path = Path(manifest_path)
    text = path.read_text()
    if not text.startswith("---"):
        raise RuntimeError(f"{path}: missing leading '---' frontmatter marker")
    end = text.find("\n---", 3)
    if end < 0:
        raise RuntimeError(f"{path}: missing closing '---' frontmatter marker")
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4:]

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    data = yaml.load(fm_text)

    now_iso = datetime.now(timezone.utc).isoformat()
    kin = (data.get("physics", {}) or {}).get("kinematics") or []
    by_id = {j.get("id"): j for j in kin}
    updated = 0
    for jid, ep in joint_endpoints.items():
        j = by_id.get(jid)
        if j is None:
            continue
        lo, hi = int(ep["min_steps"]), int(ep["max_steps"])
        if lo > hi:  # CONTRACT: min_steps < max_steps NUMERICALLY (resolver requires it)
            lo, hi = hi, lo
        j["min_steps"] = lo
        j["max_steps"] = hi
        j["endpoint_source"] = "commissioned"
        j["commissioned_at"] = now_iso
        updated += 1

    if gripper:
        g = (data.get("physics", {}) or {}).get("solver", {}).get("gripper")
        if g is not None:
            for k in ("open_steps", "close_steps", "close_steps_empty"):
                if k in gripper and gripper[k] is not None:
                    g[k] = int(gripper[k])

    import io

    buf = io.StringIO()
    yaml.dump(data, buf)
    path.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)
    return updated


def _endpoints_from_probes(probed: list[dict], fm: dict) -> tuple[dict, dict]:
    """Build (joint_endpoints, gripper) write-back payloads from probe results.

    Gripper: close-probe present → close_steps_empty + the kinematics min_steps; open-probe
    present → open_steps + the kinematics max_steps. The existing solver.gripper.close_steps
    (the grasp tick) is PRESERVED — an empty commission cannot measure it.
    """
    joint_endpoints: dict[str, dict] = {}
    gripper_solver = (fm.get("physics") or {}).get("solver", {}).get("gripper") or {}
    gripper: dict = {}
    for p in probed:
        lo, hi = p["min_present"], p["max_present"]
        if lo is None or hi is None:
            continue
        joint_endpoints[p["joint_id"]] = {"min_steps": lo, "max_steps": hi}
        if p["is_gripper"]:
            gripper = {
                "open_steps": hi,                       # open-probe present
                "close_steps_empty": lo,                # empty-jaw floor (close-probe present)
                "close_steps": gripper_solver.get("close_steps"),  # PRESERVE grasp tick
            }
    return joint_endpoints, gripper


def _write_evidence(probed: list[dict]) -> Path | None:
    """Persist a durable commission evidence file. Returns its path (best-effort)."""
    try:
        COMMISSION_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = COMMISSION_DIR / f"{stamp}.json"
        payload = [
            {"joint_id": p["joint_id"], "min_present": p["min_present"],
             "max_present": p["max_present"],
             "checks": [{"status": c.status, "detail": c.detail} for c in p["checks"]]}
            for p in probed
        ]
        path.write_text(json.dumps({"captured_at": stamp, "joints": payload}, indent=2))
        return path
    except OSError:
        return None


def cli_commission(
    manifest_path: str, *, self_test: bool = False, write: bool = False,
    dry_run: bool = False, no_deploy: bool = False,
) -> int:
    """Entry point. Exit codes: 0 ok | 2 manifest/arg error | 3 gateway/probe failure."""
    from robot_md.doctor import exit_code, run_all
    from robot_md.parser import parse_file

    if write:
        self_test = True
    if not (self_test or dry_run):
        print("commission: pass --self-test, --write, or --dry-run")
        return 2

    try:
        fm = parse_file(manifest_path).frontmatter
    except Exception as exc:
        print(f"commission: cannot parse {manifest_path}: {exc}")
        return 2

    plans = probe_targets(fm)
    if not plans:
        print("commission: no probable joints (need physics.kinematics with servo_id + "
              "zero_pose_steps, and solver.gripper for the gripper)")
        return 2

    if dry_run:
        print("commission plan (dry-run, no motion):")
        for p in plans:
            kind = "gripper(ticks)" if p["is_gripper"] else "joint"
            print(f"  {p['joint_id']:<14} motor {p['motor_id']}  {kind}  "
                  f"probe→{p['target_min']} (dir -1) then →{p['target_max']} (dir +1)")
        return 0

    probed: list[dict] = []
    try:
        for p in plans:
            probed.append(probe_joint(p))
    except Exception as exc:
        print(f"commission: gateway/probe failure: {exc}")
        return 3

    # Report.
    glyph = {"pass": "✓", "warn": "⚠", "fail": "✗"}
    any_fail = False
    for p in probed:
        for c in p["checks"]:
            print(f"  {glyph.get(c.status, '?')} {c.name}: {c.detail}")
            any_fail = any_fail or c.status == "fail"
    ev = _write_evidence(probed)
    if ev:
        print(f"  evidence → {ev}")

    if not write:
        return 3 if any_fail else 0

    if any_fail:
        print("commission: refusing to --write with a FAIL probe (fix wiring/ID first)")
        return 3

    joint_endpoints, gripper = _endpoints_from_probes(probed, fm)
    n = write_commissioned_to_manifest(manifest_path, joint_endpoints, gripper)
    print(f"commission: wrote {n} joint endpoint(s) + gripper floor to {manifest_path}")

    from robot_md.provenance import resign_and_deploy

    res = resign_and_deploy(Path(manifest_path), deploy=not no_deploy)
    print(f"commission: re-signed (kid {res['kid']}); "
          f"deployed={res['deployed']} → {res.get('deploy_path')}")

    results = run_all(Path(manifest_path))
    for c in results:
        if c.bucket == "commission":
            print(f"  doctor {glyph.get(c.status, '?')} {c.name}: {c.detail}")
    return exit_code(results, strict=False)
