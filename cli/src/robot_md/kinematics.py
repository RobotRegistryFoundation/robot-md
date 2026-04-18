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
    axis: str              # "x" | "y" | "z"
    length_mm: float       # link length from this joint to the next
    limits_rad: tuple[float, float]
    servo_id: int | None
    encoder_sign: int      # +1 or -1
    zero_pose_steps: int
    steps_per_rev: int

    def steps_to_rad(self, steps: int) -> float:
        """Encoder reading → joint angle in radians, per this joint's calibration."""
        delta = (steps - self.zero_pose_steps) * self.encoder_sign
        return delta * (2 * math.pi / self.steps_per_rev)

    def rad_to_steps(self, rad: float) -> int:
        """Joint angle → encoder target."""
        delta_steps = rad / (2 * math.pi / self.steps_per_rev)
        return int(round(self.zero_pose_steps + self.encoder_sign * delta_steps))


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
            self.joints.append(
                Joint(
                    id=jid,
                    axis=axis,
                    length_mm=float(j.get("length_mm", 0.0)),
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
        n = len(self.joints)
        for i, j in enumerate(self.joints):
            is_gripper = (self.gripper_joint_id is not None and j.id == self.gripper_joint_id)
            theta = 0.0 if is_gripper else angles_rad.get(j.id, 0.0)
            T = T @ _rot_about(j.axis, theta)
            if is_gripper:
                # Apply the gripper tip offset in the previous (wrist) frame
                dx, dy, dz = self.gripper_tip_offset_mm
                T = T @ _trans(dx, dy, dz)
                break
            else:
                T = T @ _trans(j.length_mm, 0.0, 0.0)
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
        L1 = self.by_id["shoulder_lift"].length_mm
        L2 = self.by_id["elbow_flex"].length_mm
        L3 = (
            self.by_id["wrist_flex"].length_mm
            + abs(self.gripper_tip_offset_mm[2])
        )

        # 1. azimuth
        pan = math.atan2(y, x)

        # 2. planar target in (r, z)
        r = math.hypot(x, y)

        # 3. "elbow target": the wrist position if the gripper points straight down
        rw = r
        zw = z + L3

        # 4. 2-link IK from shoulder to wrist. Shoulder origin = (0, 0).
        d2 = rw * rw + zw * zw
        d = math.sqrt(d2)
        if d > L1 + L2 - 1e-6:
            raise KinematicsError(f"target unreachable: need {d:.1f}mm, max {L1+L2:.1f}mm")
        if d < abs(L1 - L2) + 1e-6:
            raise KinematicsError(f"target too close: need {d:.1f}mm, min {abs(L1-L2):.1f}mm")

        # Law of cosines for elbow angle (interior angle at elbow)
        cos_elbow_int = (L1 * L1 + L2 * L2 - d2) / (2.0 * L1 * L2)
        cos_elbow_int = max(-1.0, min(1.0, cos_elbow_int))
        elbow_int = math.acos(cos_elbow_int)
        # elbow_flex is the signed deviation from straight arm:
        # elbow_int = pi ⇒ straight ⇒ elbow_flex = 0
        elbow_flex = math.pi - elbow_int

        # Shoulder lift: angle of line to wrist minus offset from cos
        alpha = math.atan2(zw, rw)                    # angle of wrist from shoulder
        cos_beta = (L1 * L1 + d2 - L2 * L2) / (2.0 * L1 * d)
        cos_beta = max(-1.0, min(1.0, cos_beta))
        beta = math.acos(cos_beta)                     # angle between L1 and line to wrist
        shoulder_lift = alpha + beta                   # elbow-up branch

        # Wrist flex: keep gripper pointing straight down
        # Sum of shoulder + elbow + wrist = pi/2 (tool axis down, if base frame z up)
        wrist_flex = (math.pi / 2) - shoulder_lift - elbow_flex

        return {
            "shoulder_pan": pan,
            "shoulder_lift": shoulder_lift,
            "elbow_flex": elbow_flex,
            "wrist_flex": wrist_flex,
        }

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
