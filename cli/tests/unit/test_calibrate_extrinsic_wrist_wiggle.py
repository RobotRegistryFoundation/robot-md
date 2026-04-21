"""Tests for capture_via_wrist_wiggle — v0.7.4 single-joint-isolation primitive.

Between depth_A and depth_B only wrist_flex moves, so the motion-delta centroid
is pure gripper. Defends against the 128mm-residual ceiling in v0.7.3 where
pose-to-pose motion delta centroided whichever arm segment dominated motion.
"""

from __future__ import annotations

import numpy as np

from robot_md.calibrate_extrinsic import capture_via_wrist_wiggle


def _so_arm101_fm():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "encoder": {"steps_per_rev": 4096},
                "gripper": {
                    "tip_offset_mm": [30.0, 0.0, 0.0],
                    "open_steps": 1700,
                    "close_steps": 1200,
                },
            },
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "axis": "z",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {
                    "id": "shoulder_lift",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "elbow_flex",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_flex",
                    "axis": "y",
                    "a_mm": 60.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_roll",
                    "axis": "x",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {"id": "gripper", "axis": "y", "a_mm": 0.0, "d_mm": 0.0, "limits_deg": [-90, 90]},
            ],
            "workspace": {"bounds_mm": {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}},
        }
    }


def _K(fx=600, cx=300, cy=200):
    return np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1]], dtype=float)


def _blob_depth(shape=(400, 600), center=(300, 200), radius=20, depth_mm=500, bg_mm=800):
    d = np.full(shape, bg_mm, dtype=np.uint16)
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    mask = np.hypot(xx - center[0], yy - center[1]) <= radius
    d[mask] = depth_mm
    return d


class _FakeBus:
    def __init__(self, joint_ids=None):
        self._positions = {
            "shoulder_pan": 2048,
            "shoulder_lift": 2048,
            "elbow_flex": 2048,
            "wrist_flex": 2048,
            "wrist_roll": 2048,
            "gripper": 2048,
        }
        self.interpolate_calls: list[tuple[dict, dict]] = []

    def read_positions(self):
        return dict(self._positions)

    def interpolate(self, start, target, *, hz=30, max_steps_per_tick=12, estop=None):
        self.interpolate_calls.append((dict(start), dict(target)))
        self._positions.update(target)


class _FakeCamera:
    def __init__(self, frames):
        self._frames = list(frames)
        self.grab_count = 0

    def grab_frame(self):
        self.grab_count += 1
        if not self._frames:
            return None
        return self._frames.pop(0)


def _pose_mid():
    return {
        "shoulder_pan": 0.0,
        "shoulder_lift": 0.2,
        "elbow_flex": -0.3,
        "wrist_flex": 0.0,
        "wrist_roll": 0.0,
        "gripper": 0.0,
    }


def test_wiggle_returns_centroid_for_motion_between_frames():
    """Blob at (200,200) in A, (260,200) in B → arrived pixels centroid near B."""
    from robot_md.kinematics import Kinematics

    kin = Kinematics(_so_arm101_fm())
    K = _K()
    depth_a = _blob_depth(center=(200, 200), depth_mm=500)
    depth_b = _blob_depth(center=(260, 200), depth_mm=500)
    bus = _FakeBus()
    cam = _FakeCamera([(None, depth_a, K), (None, depth_b, K)])

    result = capture_via_wrist_wiggle(bus, cam, kin, _pose_mid())
    _wiggled_pose, centroid, confidence = result
    assert centroid is not None, "expected detection from wiggle"
    u = centroid[0] * K[0, 0] / centroid[2] + K[0, 2]
    v = centroid[1] * K[1, 1] / centroid[2] + K[1, 2]
    assert 240 <= u <= 280, f"centroid u={u} not near blob B center 260"
    assert 180 <= v <= 220
    assert confidence > 0.0


def test_wiggle_returns_wiggled_pose_with_wrist_flex_shifted():
    """Returned pose dict must reflect the post-wiggle wrist_flex angle."""
    from robot_md.kinematics import Kinematics

    kin = Kinematics(_so_arm101_fm())
    K = _K()
    depth_a = _blob_depth(center=(200, 200))
    depth_b = _blob_depth(center=(260, 200))
    bus = _FakeBus()
    cam = _FakeCamera([(None, depth_a, K), (None, depth_b, K)])

    pose = _pose_mid()
    wiggled_pose, _centroid, _confidence = capture_via_wrist_wiggle(
        bus, cam, kin, pose, wiggle_rad=0.15
    )
    assert wiggled_pose is not None
    assert abs(wiggled_pose["wrist_flex"] - (pose["wrist_flex"] + 0.15)) < 1e-9
    # Other joints unchanged.
    for j in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_roll"):
        assert wiggled_pose[j] == pose[j]


def test_wiggle_returns_none_when_wrist_flex_missing():
    """Kinematics without wrist_flex joint → (None, None, 0.0)."""
    from robot_md.kinematics import Kinematics

    fm = _so_arm101_fm()
    fm["physics"]["kinematics"] = [
        j for j in fm["physics"]["kinematics"] if j["id"] != "wrist_flex"
    ]
    kin = Kinematics(fm)
    bus = _FakeBus()
    cam = _FakeCamera([])

    result = capture_via_wrist_wiggle(bus, cam, kin, _pose_mid())
    assert result == (None, None, 0.0)


def test_wiggle_uses_negative_delta_near_upper_limit():
    """Pose at upper limit of wrist_flex → wiggle picks -Δ, not +Δ."""
    from robot_md.kinematics import Kinematics

    kin = Kinematics(_so_arm101_fm())
    K = _K()
    depth_a = _blob_depth(center=(200, 200))
    depth_b = _blob_depth(center=(260, 200))
    bus = _FakeBus()
    cam = _FakeCamera([(None, depth_a, K), (None, depth_b, K)])

    # wrist_flex limit is +90° (~1.57 rad); set pose very near top.
    pose = _pose_mid()
    pose["wrist_flex"] = 1.50  # 0.07 rad below the upper limit
    wiggled_pose, _centroid, _confidence = capture_via_wrist_wiggle(
        bus, cam, kin, pose, wiggle_rad=0.15
    )
    assert wiggled_pose is not None
    assert wiggled_pose["wrist_flex"] < pose["wrist_flex"], (
        "wiggle should flip sign when +Δ exceeds limit"
    )
    assert abs(wiggled_pose["wrist_flex"] - (pose["wrist_flex"] - 0.15)) < 1e-9


def test_wiggle_returns_none_when_both_directions_exceed_limits():
    """Wrist at a limit with no room either side → (None, None, 0.0)."""
    from robot_md.kinematics import Kinematics

    fm = _so_arm101_fm()
    # Shrink wrist_flex envelope to ±0.05 rad so 0.15-rad wiggle can't fit either direction.
    for j in fm["physics"]["kinematics"]:
        if j["id"] == "wrist_flex":
            # limits_deg ±2.86°  → ±0.05 rad
            j["limits_deg"] = [-2.86, 2.86]
    kin = Kinematics(fm)
    bus = _FakeBus()
    cam = _FakeCamera([])

    result = capture_via_wrist_wiggle(bus, cam, kin, _pose_mid(), wiggle_rad=0.15)
    assert result == (None, None, 0.0)


def test_wiggle_returns_none_when_camera_grab_fails():
    """camera.grab_frame() returning None at either step → (None, None, 0.0)."""
    from robot_md.kinematics import Kinematics

    kin = Kinematics(_so_arm101_fm())
    bus = _FakeBus()
    # Only one frame available; second grab returns None.
    cam = _FakeCamera([(None, _blob_depth(), _K())])

    result = capture_via_wrist_wiggle(bus, cam, kin, _pose_mid())
    assert result == (None, None, 0.0)


def test_wiggle_issues_two_interpolate_calls():
    """First call: move-to-pose. Second call: wiggle wrist_flex by ±Δ."""
    from robot_md.kinematics import Kinematics

    kin = Kinematics(_so_arm101_fm())
    K = _K()
    bus = _FakeBus()
    cam = _FakeCamera(
        [
            (None, _blob_depth(center=(200, 200)), K),
            (None, _blob_depth(center=(260, 200)), K),
        ]
    )

    capture_via_wrist_wiggle(bus, cam, kin, _pose_mid(), wiggle_rad=0.15)
    assert len(bus.interpolate_calls) == 2, (
        f"expected 2 interpolate() calls (move-to-pose + wiggle), got {len(bus.interpolate_calls)}"
    )
    # In the second call only wrist_flex should differ from the first call's target.
    _start1, target1 = bus.interpolate_calls[0]
    _start2, target2 = bus.interpolate_calls[1]
    differing = {k for k in target2 if target2[k] != target1.get(k)}
    assert differing == {"wrist_flex"}, f"wiggle moved joints other than wrist_flex: {differing}"
