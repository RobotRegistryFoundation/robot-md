"""Tests for doctor.check_joint_ranges — the passive (no-motion) `commission` bucket.

Makes two reality gaps visible in plain `robot-md doctor`, without touching hardware:
  * the silent gripper bug — "close" declared as a WIDER (>=) tick than "open", so the
    jaws would never shut (the root cause of the whole pick-place saga);
  * joints whose tick endpoints were never reality-checked (preset_default / missing).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md import doctor


def test_close_steps_ge_open_steps_warns():
    # The silent bug class: "close" is NOT a narrower (lower) tick than "open".
    fm = {"physics": {"solver": {"gripper": {"open_steps": 1700, "close_steps": 2048}}}}
    results = doctor.check_joint_ranges(fm)
    grip_warns = [r for r in results if r.status == "warn" and "gripper" in r.name.lower()]
    assert grip_warns, "expected a gripper WARN when close_steps >= open_steps"
    assert all(r.bucket == "commission" for r in results)


def test_healthy_gripper_close_narrower_than_open_passes():
    fm = {"physics": {"solver": {"gripper": {"open_steps": 1697, "close_steps": 1529}}}}
    results = doctor.check_joint_ranges(fm)
    grip = [r for r in results if "gripper" in r.name.lower()]
    assert grip and grip[0].status == "pass"


def test_preset_default_endpoints_warn():
    fm = {
        "physics": {
            "kinematics": [
                {"id": "shoulder_pan", "endpoint_source": "preset_default"},
                {
                    "id": "elbow_flex",
                    "endpoint_source": "commissioned",
                    "min_steps": 1100,
                    "max_steps": 3000,
                },
            ]
        }
    }
    results = doctor.check_joint_ranges(fm)
    assert any(r.status == "warn" for r in results)


def test_missing_endpoints_warn():
    # No min_steps/max_steps and no endpoint_source => not reality-checked.
    fm = {"physics": {"kinematics": [{"id": "shoulder_pan"}]}}
    results = doctor.check_joint_ranges(fm)
    assert any(r.status == "warn" for r in results)


def test_all_commissioned_endpoints_pass():
    fm = {
        "physics": {
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "endpoint_source": "commissioned",
                    "min_steps": 1100,
                    "max_steps": 3000,
                },
                {
                    "id": "elbow_flex",
                    "endpoint_source": "commissioned",
                    "min_steps": 1200,
                    "max_steps": 2900,
                },
            ]
        }
    }
    results = doctor.check_joint_ranges(fm)
    endpoint_checks = [r for r in results if "endpoint" in r.name.lower()]
    assert endpoint_checks and all(r.status == "pass" for r in endpoint_checks)


def test_no_manifest_returns_empty():
    assert doctor.check_joint_ranges(None) == []


def test_all_results_use_commission_bucket():
    fm = {
        "physics": {
            "solver": {"gripper": {"open_steps": 1697, "close_steps": 1529}},
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "endpoint_source": "commissioned",
                    "min_steps": 1,
                    "max_steps": 4000,
                }
            ],
        }
    }
    results = doctor.check_joint_ranges(fm)
    assert results and all(r.bucket == "commission" for r in results)


def test_inverted_arm_endpoints_warn_even_when_marked_commissioned():
    # min_steps >= max_steps is invalid travel: the actuator silently skips it to default,
    # so doctor must make the bad commissioning VISIBLE (not report 'all commissioned').
    fm = {
        "physics": {
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "endpoint_source": "commissioned",
                    "min_steps": 3000,
                    "max_steps": 1000,
                }
            ]
        }
    }
    results = doctor.check_joint_ranges(fm)
    assert any(r.status == "warn" for r in results)
    assert all(r.bucket == "commission" for r in results)


def test_run_all_wires_in_commission_bucket():
    # Regression guard: the check must actually be invoked by run_all, not just defined.
    bob = Path(__file__).parent.parent.parent / "examples" / "bob.ROBOT.md"
    if not bob.exists():
        pytest.skip("examples/bob.ROBOT.md not in this tree")
    results = doctor.run_all(bob)
    assert any(r.bucket == "commission" for r in results)
