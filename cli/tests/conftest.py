"""Pytest fixtures shared across test files."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Stub out hardware-only optional deps when the extra isn't installed so unit
# tests that go through load_context() don't blow up on import. The backend
# still fails to actually talk to hardware — that's expected; hardware tests
# are gated behind --run-hardware and the real modules.
if importlib.util.find_spec("feetech_servo_sdk") is None:
    _fake_feetech = MagicMock()
    _fake_port = MagicMock()
    _fake_port.openPort.return_value = True
    _fake_port.setBaudRate.return_value = True
    _fake_feetech.PortHandler.return_value = _fake_port
    _fake_ph = MagicMock()
    _fake_ph.read2ByteTxRx.return_value = (2048, 0, 0)
    _fake_feetech.PacketHandler.return_value = _fake_ph
    sys.modules.setdefault("feetech_servo_sdk", _fake_feetech)


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: requires physical robot hardware; opt-in")
    config.addinivalue_line("markers", "integration: integration test (local subprocess OK)")


def pytest_addoption(parser):
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.hardware",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware", default=False):
        return
    if os.environ.get("RM_HARDWARE") == "1":
        return
    skip_hw = pytest.mark.skip(reason="hardware tests require --run-hardware or RM_HARDWARE=1")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hw)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).parent.parent.parent / "examples"
