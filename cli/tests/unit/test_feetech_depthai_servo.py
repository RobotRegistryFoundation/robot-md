from __future__ import annotations

import sys
from unittest.mock import MagicMock

from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def _install_fake_sdk(monkeypatch):
    fake_sdk = MagicMock()
    fake_port = MagicMock()
    fake_port.openPort.return_value = True
    fake_port.setBaudRate.return_value = True
    fake_sdk.PortHandler.return_value = fake_port
    fake_sms = MagicMock()
    fake_sms.read2ByteTxRx.return_value = (2048, 0, 0)
    fake_sms_module = MagicMock()
    fake_sms_module.sms_sts.return_value = fake_sms
    monkeypatch.setitem(sys.modules, "scservo_sdk", fake_sdk)
    monkeypatch.setitem(sys.modules, "scservo_sdk.sms_sts", fake_sms_module)
    return fake_sdk, fake_port, fake_sms


def test_open_from_spec_opens_port(monkeypatch, fixtures_dir):
    fake_sdk, fake_port, _ = _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    fake_sdk.PortHandler.assert_called_once_with(bus.port)
    fake_port.openPort.assert_called_once()
    fake_port.setBaudRate.assert_called_once_with(bus.baud)
    bus.close()


def test_read_positions_returns_named_dict(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    positions = bus.read_positions()
    assert set(positions.keys()) == {
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    }
    assert all(v == 2048 for v in positions.values())
    bus.close()


def test_read_positions_skips_nonresponders(monkeypatch, fixtures_dir):
    _, _, fake_ph = _install_fake_sdk(monkeypatch)

    def _fake_read(sid, addr):
        if sid == 3:
            return (0, 1, 0)
        return (2048, 0, 0)

    fake_ph.read2ByteTxRx.side_effect = _fake_read
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    positions = bus.read_positions()
    assert "elbow_flex" not in positions
    assert "shoulder_pan" in positions
    assert len(positions) == 5
    bus.close()


def test_write_positions_sends_goal(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ADDR_GOAL_POSITION, ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    bus.write_positions({"shoulder_pan": 2100, "gripper": 1700})
    calls = bus._ph.write2ByteTxRx.call_args_list
    sids = sorted(c.args[0] for c in calls)
    assert sids == [1, 6]
    assert all(c.args[1] == ADDR_GOAL_POSITION for c in calls)
    bus.close()


def test_torque_writes_all_servos(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ADDR_TORQUE_ENABLE, ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()
    bus.torque(True)
    calls = bus._ph.write1ByteTxRx.call_args_list
    assert len(calls) == 6
    assert all(c.args[1] == ADDR_TORQUE_ENABLE for c in calls)
    assert all(c.args[2] == 1 for c in calls)
    bus.close()


def test_interpolate_respects_estop(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()

    class _Estop:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 3

    estop = _Estop()
    start = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    target = {**start, "shoulder_pan": 2200}

    bus.interpolate(start, target, hz=200, max_steps_per_tick=5, estop=estop)
    assert bus._ph.write2ByteTxRx.call_count <= 6 * 4
    bus.close()


def test_interpolate_interpolates_monotonic(monkeypatch, fixtures_dir):
    _install_fake_sdk(monkeypatch)
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus.from_spec(_spec(fixtures_dir))
    bus.open()

    class _NoopEstop:
        def is_set(self):
            return False

    start = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    target = {**start, "shoulder_pan": 2200}
    bus.interpolate(start, target, hz=200, max_steps_per_tick=10, estop=_NoopEstop())

    shoulder_writes = [c.args[2] for c in bus._ph.write2ByteTxRx.call_args_list if c.args[0] == 1]
    assert shoulder_writes[0] > 2048 and shoulder_writes[-1] == 2200
    assert all(
        shoulder_writes[i] <= shoulder_writes[i + 1] for i in range(len(shoulder_writes) - 1)
    )
    bus.close()
