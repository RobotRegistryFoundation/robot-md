"""Translate RobotSpec → LeRobot make_robot() config dict."""

from __future__ import annotations

from robot_md.robot_spec import RobotSpec

_ARM_PROTOCOLS = frozenset({"feetech", "dynamixel"})


def build_lerobot_config(spec: RobotSpec) -> dict:
    """Pull port + baud_rate + per-joint servo mapping out of a RobotSpec.

    Driver gives transport (port, baud_rate, model, count); physics.kinematics
    gives the joint id ↔ servo_id mapping. Both sources are required.
    """
    arm_driver = next(
        (d for d in spec.drivers if d.protocol in _ARM_PROTOCOLS),
        None,
    )
    if arm_driver is None:
        raise ValueError(
            "RobotSpec has no feetech/dynamixel arm driver; LeRobot adapter requires one"
        )
    if not spec.physics.kinematics:
        raise ValueError(
            f"Driver {arm_driver.id!r} declared but physics.kinematics is empty; "
            "cannot build per-motor mapping"
        )
    motors = [
        {
            "joint": kin["id"],
            "servo_id": kin["servo_id"],
            "model": arm_driver.model,
        }
        for kin in spec.physics.kinematics
    ]
    return {
        "robot_type": "so_arm",
        "port": arm_driver.port,
        "baud_rate": arm_driver.baud_rate,
        "model": arm_driver.model,
        "motors": motors,
    }
