# cli/tests/backends/test_realsense_open_mocked.py
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from robot_md.robot_spec import (
    MetadataBlock,
    PhysicsBlock,
    RobotSpec,
    SafetyBlock,
    VisionBlock,
)


def _make_minimal_spec(rrn: str) -> RobotSpec:
    """Create a minimal RobotSpec for testing."""
    return RobotSpec(
        rcan_version="3.1",
        metadata=MetadataBlock(
            robot_name="test",
            rrn=rrn,
            device_id=None,
            manufacturer=None,
            model=None,
            version=None,
            license=None,
        ),
        physics=PhysicsBlock(
            type="",
            dof=0,
            kinematics=(),
            solver={},
            cameras=(),
            poses={},
            workspace=None,
        ),
        drivers=(),
        safety=SafetyBlock(
            max_joint_velocity_dps=None,
            max_linear_velocity_ms=None,
            payload_kg=None,
            workspace_bounds_m=None,
            failsafe_behavior=None,
            estop_software=False,
            estop_hardware=False,
            estop_response_ms=0,
            hitl_gates=(),
        ),
        capabilities=frozenset(),
        brain=None,
        raw_yaml="",
        capability_contracts={},
        vision=VisionBlock(object_descriptors=()),
        learned_skills=(),
    )


def _install_fake_pyrealsense2(monkeypatch) -> tuple[MagicMock, MagicMock]:
    fake = types.ModuleType("pyrealsense2")
    pipeline = MagicMock(name="rs.pipeline_instance")
    pipeline_factory = MagicMock(name="rs.pipeline_factory", return_value=pipeline)
    config = MagicMock(name="rs.config_instance")
    config_factory = MagicMock(name="rs.config_factory", return_value=config)
    fake.pipeline = pipeline_factory
    fake.config = config_factory

    class _Stream:
        color = "color"
        depth = "depth"

    class _Format:
        bgr8 = "bgr8"
        z16 = "z16"

    fake.stream = _Stream()
    fake.format = _Format()
    monkeypatch.setitem(sys.modules, "pyrealsense2", fake)
    return pipeline, config


def test_open_starts_pipeline_with_color_and_depth_streams(monkeypatch) -> None:
    pipeline, config = _install_fake_pyrealsense2(monkeypatch)
    from robot_md.backends.realsense import RealsenseBackend

    spec = _make_minimal_spec(rrn="RRN-test")
    b = RealsenseBackend()
    b.open(spec)

    pipeline.start.assert_called_once()
    args, _ = pipeline.start.call_args
    assert args[0] is config

    enable_calls = config.enable_stream.call_args_list
    enabled = {call.args[0] for call in enable_calls}
    assert enabled == {"color", "depth"}


def test_close_stops_pipeline(monkeypatch) -> None:
    pipeline, _ = _install_fake_pyrealsense2(monkeypatch)
    from robot_md.backends.realsense import RealsenseBackend

    b = RealsenseBackend()
    b.open(_make_minimal_spec(rrn="RRN-test"))
    b.close()
    pipeline.stop.assert_called_once()
