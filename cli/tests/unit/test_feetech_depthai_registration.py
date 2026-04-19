from __future__ import annotations


def test_feetech_depthai_is_registered():
    from robot_md.backends.registry import discover_backends

    names = {b.name for b in discover_backends()}
    assert "feetech_depthai" in names


def test_feetech_depthai_declares_protocols():
    from robot_md.backends.feetech_depthai import FeetechDepthaiBackend

    backend = FeetechDepthaiBackend()
    assert backend.protocols == frozenset({"feetech", "depthai"})
    assert "arm.pick" in backend.capabilities()
    assert "arm.place" in backend.capabilities()
    assert "vision.describe" in backend.capabilities()
    assert "status.report" in backend.capabilities()
