from __future__ import annotations

from importlib.metadata import entry_points


def test_lerobot_and_realsense_entry_points_registered() -> None:
    eps = entry_points(group="robot_md.backends")
    names = {ep.name for ep in eps}
    assert "feetech_depthai" in names  # baseline
    assert "lerobot" in names
    assert "realsense" in names
