"""Baseline kinematics solver reading `physics.solver` from a ROBOT.md.

A planner with nothing but a validated ROBOT.md (no URDF, no MoveIt, no ikpy)
can instantiate :class:`Kinematics` and get:

  * **Step↔angle conversions** (solid) — honors per-joint `encoder_sign` and
    `zero_pose_steps`. This is always correct regardless of chain topology.
  * **Forward kinematics** — simple N-link chain where each joint rotates
    about its `axis` and the next joint is offset `length_mm` along the
    current link's local +x. Works for chains where `length_mm` = horizontal
    reach. *Does not handle joints where the link extends along the joint's
    rotation axis* (e.g. a vertical riser from a z-rotation shoulder_pan to
    the shoulder_lift joint). For those robots, v1.1 should extend the
    schema with per-joint `a_mm` + `d_mm` DH parameters.
  * **Inverse kinematics** — 3-link planar fallback (shoulder_lift,
    elbow_flex, wrist_flex) with azimuth from shoulder_pan. Assumes a
    SO-ARM101-style topology: first joint rotates about z for azimuth, next
    two rotate about y in the sagittal plane, fourth is a wrist pitch. For
    other chains, pass `Kinematics` the parsed manifest and write the IK
    yourself against the `joints` list.

For general 6-DoF reachability, bring ikpy or MoveIt — this module is the
baseline, not the ceiling. Its value is that it works from the ROBOT.md
*alone*, so a planner on any host can do basic FK/step-conversion without
installing robot-specific dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class KinematicsError(Exception):
    """Target unreachable, config missing, or convention unsupported."""


@dataclass
class Joint:
    id: str
    axis: str  # "x" | "y" | "z"
    a_mm: float  # DH a: perpendicular to rotation axis (horizontal reach)
    d_mm: float  # DH d: along rotation axis (axial offset)
    limits_rad: tuple[float, float]
    servo_id: int | None
    encoder_sign: int  # +1 or -1
    zero_pose_steps: int
    steps_per_rev: int

    @property
    def length_mm(self) -> float:
        """Legacy accessor — equals a_mm when d_mm=0. Kept for backward compat."""
        return self.a_mm

    def steps_to_rad(self, steps: int) -> float:
        """Encoder reading → joint angle in radians, per this joint's calibration."""
        delta = (steps - self.zero_pose_steps) * self.encoder_sign
        return delta * (2 * math.pi / self.steps_per_rev)

    def rad_to_steps(self, rad: float) -> int:
        """Joint angle → encoder target."""
        delta_steps = rad / (2 * math.pi / self.steps_per_rev)
        return round(self.zero_pose_steps + self.encoder_sign * delta_steps)


@dataclass
class EnvelopeRisk:
    """Result of a pre-flight envelope analysis.

    level:
      - "ok":            all joints well within envelope
      - "latch_warning": any joint exceeds 85% of envelope on a
                         sustained hold — high risk of STS3215
                         overload latch under gravity load
      - "out_of_limits": at least one joint outside declared limits_rad
    """

    level: str  # "ok" | "latch_warning" | "out_of_limits"
    joint: str | None
    angle_rad: float | None
    reason: str


class Kinematics:
    """Baseline FK/IK driven by ROBOT.md's `physics.solver` + `physics.kinematics[]`."""

    def __init__(self, parsed: Any):
        """`parsed` is a dict — the frontmatter of a ROBOT.md."""
        phys = parsed.get("physics") or {}
        solver = phys.get("solver") or {}
        kin = phys.get("kinematics") or []
        if not kin:
            raise KinematicsError("physics.kinematics[] is empty or missing")

        conv = solver.get("convention", "DH")
        if conv not in ("DH", "custom"):
            # URDF is a ref-out case; we don't implement it here
            raise KinematicsError(f"unsupported kinematic convention: {conv}")

        enc = solver.get("encoder") or {}
        default_steps = int(enc.get("steps_per_rev", 4096))

        self.joints: list[Joint] = []
        for j in kin:
            jid = j.get("id")
            if not jid:
                raise KinematicsError("kinematics[] item missing `id`")
            axis = j.get("axis", "y")
            limits_deg = j.get("limits_deg") or [-180, 180]
            # DH params (v1.1): prefer a_mm/d_mm, fall back to legacy length_mm for a.
            legacy = float(j.get("length_mm", 0.0))
            a_mm = float(j["a_mm"]) if "a_mm" in j else legacy
            d_mm = float(j.get("d_mm", 0.0))
            self.joints.append(
                Joint(
                    id=jid,
                    axis=axis,
                    a_mm=a_mm,
                    d_mm=d_mm,
                    limits_rad=(math.radians(limits_deg[0]), math.radians(limits_deg[1])),
                    servo_id=j.get("servo_id"),
                    encoder_sign=int(j.get("encoder_sign", 1)),
                    zero_pose_steps=int(j.get("zero_pose_steps", default_steps // 2)),
                    steps_per_rev=default_steps,
                )
            )
        self.by_id: dict[str, Joint] = {j.id: j for j in self.joints}

        grip = solver.get("gripper") or {}
        self.gripper_joint_id: str | None = grip.get("joint_id")
        self.gripper_tip_offset_mm: list[float] = list(grip.get("tip_offset_mm") or [0.0, 0.0, 0.0])
        self.gripper_open_steps: int | None = grip.get("open_steps")
        self.gripper_close_steps: int | None = grip.get("close_steps")

        cam = solver.get("camera") or {}
        self.camera_mount: str = cam.get("mount", "world")
        self.camera_extrinsic: list[float] | None = cam.get("extrinsic")

    # ------------------------------------------------------------------ FK

    def fk(self, angles_rad: dict[str, float]) -> tuple[float, float, float]:
        """Forward kinematics → (x, y, z) of the tip, in arm-base frame (mm).

        Chain semantics:
          * Joints are applied in the order they appear in `kinematics[]`.
          * Each joint rotates about its `axis` in its local frame.
          * Translation to the next joint is `length_mm` along the local +x axis
            (standard DH; base_frame.forward = x assumed).
          * The last rotation (the gripper joint) is treated as passive — its
            angle does not move the tip; the tip sits at `gripper.tip_offset_mm`
            from the previous wrist frame.
        """
        # Accumulated 4x4 transform as a 3x3 rotation + 3-vector translation,
        # stored flat: (R, t) with R a 3x3 nested tuple.
        import numpy as np

        T = np.eye(4)
        for j in self.joints:
            is_gripper = self.gripper_joint_id is not None and j.id == self.gripper_joint_id
            theta = 0.0 if is_gripper else angles_rad.get(j.id, 0.0)
            T = T @ _rot_about(j.axis, theta)
            if is_gripper:
                # Apply the gripper tip offset in the previous (wrist) frame
                dx, dy, dz = self.gripper_tip_offset_mm
                T = T @ _trans(dx, dy, dz)
                break
            # DH-style step: a along +x, then d along +z (in the local frame after rotation)
            T = T @ _trans(j.a_mm, 0.0, j.d_mm)
        return float(T[0, 3]), float(T[1, 3]), float(T[2, 3])

    # ------------------------------------------------------------------ IK

    def ik_reach(self, target_xyz_mm: tuple[float, float, float]) -> dict[str, float]:
        """Baseline IK — 3-link planar in the sagittal plane + azimuth.

        Assumes the chain has joints named `shoulder_pan` (azimuth, axis z),
        `shoulder_lift`, `elbow_flex`, and `wrist_flex` — the canonical
        SO-ARM101-style topology. Returns a dict of joint_id → angle_rad
        covering those four. Remaining joints (wrist_roll, gripper) are
        untouched by the solver; the caller decides roll + grip state.

        Strategy:
          1. shoulder_pan = atan2(y_target, x_target) — aim the arm at the
             target azimuth.
          2. Reduce to a planar 3-link problem in the (r, z) plane with
             r = sqrt(x^2 + y^2). Links are L1 (shoulder_lift → elbow),
             L2 (elbow → wrist), L3 (wrist → tip, including gripper offset).
          3. Choose wrist orientation: gripper points straight down
             (wrist_flex complements shoulder_lift + elbow_flex so the
             tool axis is vertical). This removes one redundancy.
          4. 2-link IK on the "elbow target" (target - L3 along -z), law of
             cosines, pick elbow-up solution.
        """
        required = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex"}
        if not required.issubset(self.by_id):
            raise KinematicsError(
                f"ik_reach requires joints {sorted(required)}; found {sorted(self.by_id)}"
            )

        x, y, z = target_xyz_mm
        L1 = self.by_id["shoulder_lift"].a_mm
        L2 = self.by_id["elbow_flex"].a_mm
        # Tool length along tool +x from the wrist_flex joint to the grasp tip.
        # Tool-frame convention: tip_offset_mm is in tool frame at zero pose,
        # where tool +x = base +x. Use the x component — after wrist_flex rotates
        # to point tool down, tool +x → base -z, so tip lands |L3| below wrist.
        L3 = (
            self.by_id["wrist_flex"].a_mm
            + self.by_id.get("wrist_roll", Joint("", "x", 0, 0, (0, 0), None, 1, 0, 1)).a_mm
            + abs(self.gripper_tip_offset_mm[0])
        )
        # Shoulder riser: if shoulder_pan has d_mm, the 2-link IK plane is elevated.
        d1 = self.by_id["shoulder_pan"].d_mm

        # 1. azimuth
        pan = math.atan2(y, x)

        # 2. planar target in (r, z) relative to shoulder_lift origin.
        r = math.hypot(x, y)

        # 3. "wrist target": where the wrist must be so the gripper points straight
        #    down and lands at (x, y, z). In arm-base frame, wrist is L3 above target.
        rw = r
        zw_base = z + L3  # wrist z in arm-base frame
        zw = zw_base - d1  # wrist z relative to shoulder joint

        # 4. 2-link IK from shoulder to wrist.
        d2 = rw * rw + zw * zw
        d = math.sqrt(d2)
        if d > L1 + L2 - 1e-6:
            raise KinematicsError(f"target unreachable: need {d:.1f}mm, max {L1 + L2:.1f}mm")
        if d < abs(L1 - L2) + 1e-6:
            raise KinematicsError(f"target too close: need {d:.1f}mm, min {abs(L1 - L2):.1f}mm")

        # Law of cosines for elbow angle (interior angle at elbow).
        cos_elbow_int = (L1 * L1 + L2 * L2 - d2) / (2.0 * L1 * L2)
        cos_elbow_int = max(-1.0, min(1.0, cos_elbow_int))
        elbow_int = math.acos(cos_elbow_int)
        elbow_flex_mag = math.pi - elbow_int  # magnitude; 0 when straight

        # Shoulder lift magnitude: angle of wrist from +r axis, plus offset.
        alpha = math.atan2(zw, rw)  # angle of wrist from +r (standard math)
        cos_beta = (L1 * L1 + d2 - L2 * L2) / (2.0 * L1 * d)
        cos_beta = max(-1.0, min(1.0, cos_beta))
        beta = math.acos(cos_beta)
        shoulder_lift_mag = alpha + beta  # elbow-up magnitude

        # FK rotates about y such that +θ swings +x toward -z (i.e., positive
        # angle = arm rotates DOWN). Standard math IK assumes +θ is up.
        # Converting: negate shoulder_lift so +z targets produce negative angles
        # (arm goes up). elbow_flex stays positive — that's the elbow-UP branch
        # in our convention.
        shoulder_lift = -shoulder_lift_mag
        elbow_flex = elbow_flex_mag
        # Tool axis (+x in wrist frame) should point along -z in base frame so
        # the gripper hangs vertically. After three y-rotations by θ_l,θ_e,θ_w:
        #     tool_x_in_base = (cos(Σθ), 0, -sin(Σθ))
        # For tool_x = (0, 0, -1) we need Σθ = π/2.
        wrist_flex = (math.pi / 2) - shoulder_lift - elbow_flex

        solved = {
            "shoulder_pan": pan,
            "shoulder_lift": shoulder_lift,
            "elbow_flex": elbow_flex,
            "wrist_flex": wrist_flex,
        }
        # Enforce declared joint limits — a solved angle outside the mechanical
        # envelope would stall or damage the servo.
        for name, angle in solved.items():
            j = self.by_id.get(name)
            if j is None:
                continue
            lo, hi = j.limits_rad
            if not (lo <= angle <= hi):
                raise KinematicsError(
                    f"ik target unreachable within joint limits: {name}="
                    f"{math.degrees(angle):+.1f}° outside "
                    f"[{math.degrees(lo):+.1f}, {math.degrees(hi):+.1f}]°"
                )
        return solved

    # -------------------------------------------------- envelope analysis

    def analyze_envelope(
        self,
        joint_cfg: dict[str, float],
        *,
        duration_ms: int = 1000,
    ) -> EnvelopeRisk:
        """Analyze a joint configuration for STS3215 latch risk.

        Hard limits (out_of_limits) are always enforced. Latch-warning fires
        when any joint exceeds 85% of its envelope AND the configuration
        will be held for more than ~500ms — transient excursions are
        allowed because gravity load takes time to trip overload
        protection. The 85% threshold is calibrated from SO-ARM101 bring-up
        where wrist_flex stalled at sustained ~80° under gravity load.
        """
        TRANSIENT_MS = 500

        # Hard-limit check first — always applies.
        for name, angle in joint_cfg.items():
            j = self.by_id.get(name)
            if j is None:
                continue
            lo, hi = j.limits_rad
            if not (lo <= angle <= hi):
                return EnvelopeRisk(
                    level="out_of_limits",
                    joint=name,
                    angle_rad=angle,
                    reason=(
                        f"{name}={math.degrees(angle):.1f}° outside limits "
                        f"[{math.degrees(lo):.1f}, {math.degrees(hi):.1f}]"
                    ),
                )

        if duration_ms <= TRANSIENT_MS:
            return EnvelopeRisk(level="ok", joint=None, angle_rad=None, reason="")

        # Latch-warning: ratio of |angle| to nearer limit > 0.85.
        for name, angle in joint_cfg.items():
            j = self.by_id.get(name)
            if j is None:
                continue
            lo, hi = j.limits_rad
            limit = hi if angle >= 0 else -lo
            if limit <= 0:
                continue
            ratio = abs(angle) / limit
            if ratio > 0.85:
                return EnvelopeRisk(
                    level="latch_warning",
                    joint=name,
                    angle_rad=angle,
                    reason=(
                        f"{name}={math.degrees(angle):.1f}° is {ratio*100:.0f}% of "
                        f"envelope ±{math.degrees(limit):.1f}° — STS3215 latch risk"
                    ),
                )

        return EnvelopeRisk(level="ok", joint=None, angle_rad=None, reason="")

    # ------------------------------------------------------------ helpers

    def angles_to_step_targets(self, angles_rad: dict[str, float]) -> dict[str, int]:
        """Convert joint angles (rad) to per-joint encoder targets (steps)."""
        out: dict[str, int] = {}
        for name, rad in angles_rad.items():
            j = self.by_id.get(name)
            if j is None:
                continue
            out[name] = j.rad_to_steps(rad)
        return out

    def steps_to_angles(self, steps: dict[str, int]) -> dict[str, float]:
        """Convert encoder readings to joint angles (rad)."""
        out: dict[str, float] = {}
        for name, s in steps.items():
            j = self.by_id.get(name)
            if j is None:
                continue
            out[name] = j.steps_to_rad(s)
        return out


# ---------------------------- small transform helpers ----------------------


def _rot_about(axis: str, theta: float):
    import numpy as np

    c, s = math.cos(theta), math.sin(theta)
    T = np.eye(4)
    if axis == "x":
        T[1, 1], T[1, 2] = c, -s
        T[2, 1], T[2, 2] = s, c
    elif axis == "y":
        T[0, 0], T[0, 2] = c, s
        T[2, 0], T[2, 2] = -s, c
    elif axis == "z":
        T[0, 0], T[0, 1] = c, -s
        T[1, 0], T[1, 1] = s, c
    else:
        raise KinematicsError(f"unknown axis {axis!r}; expected x|y|z")
    return T


def _trans(dx: float, dy: float, dz: float):
    import numpy as np

    T = np.eye(4)
    T[0, 3], T[1, 3], T[2, 3] = dx, dy, dz
    return T
