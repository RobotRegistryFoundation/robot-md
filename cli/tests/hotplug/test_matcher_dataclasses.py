from __future__ import annotations

import dataclasses

import pytest

from robot_md.hotplug.matcher import BindProposal, Decision


def test_bind_proposal_is_frozen() -> None:
    bp = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="arm_servos",
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0"},
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        bp.backend_name = "feetech_depthai"


def test_decision_dataclass_shape() -> None:
    d = Decision(tier="HIGH", unambiguous=True, bind_proposal=None, alternatives=[], reasons=[])
    assert d.tier == "HIGH"
    assert d.alternatives == []
