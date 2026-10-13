"""Pytest fixtures shared across test files."""

from __future__ import annotations

import importlib.util
import ipaddress
import os
import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Stub out hardware-only optional deps when the extra isn't installed so unit
# tests that go through load_context() don't blow up on import. The backend
# still fails to actually talk to hardware — that's expected; hardware tests
# are gated behind --run-hardware and the real modules.
#
# PyPI dist `feetech-servo-sdk` ships the `scservo_sdk` Python module; we use
# `scservo_sdk.sms_sts.sms_sts` directly because the bare `PacketHandler()`
# factory in scservo_sdk is broken upstream.
if importlib.util.find_spec("scservo_sdk") is None:
    _fake_scservo = MagicMock()
    _fake_port = MagicMock()
    _fake_port.openPort.return_value = True
    _fake_port.setBaudRate.return_value = True
    _fake_scservo.PortHandler.return_value = _fake_port
    _fake_sms = MagicMock()
    _fake_sms.read2ByteTxRx.return_value = (2048, 0, 0)
    _fake_sms_module = MagicMock()
    _fake_sms_module.sms_sts.return_value = _fake_sms
    sys.modules.setdefault("scservo_sdk", _fake_scservo)
    sys.modules.setdefault("scservo_sdk.sms_sts", _fake_sms_module)


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: requires physical robot hardware; opt-in")
    config.addinivalue_line("markers", "integration: integration test (local subprocess OK)")
    config.addinivalue_line(
        "markers", "live_network: may reach non-loopback hosts (opt-in; never prod RRF)"
    )


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


# ---- no live network (#100) ------------------------------------------------
#
# A test that forgot to patch one RRF call used to reach the real
# robotregistryfoundation.org: it hung CI runners and, when the network
# worked, wrote junk authority records to the PUBLIC registry on every local
# run. Patching each call site is not enough (new steps get added to
# cli_register and the old tests keep passing), so the suite refuses
# non-loopback hosts outright and FAILS the test that tried. Loopback and
# unix sockets are fine (local servers, subprocess fixtures).
_LOOPBACK_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode()
    host = str(host).strip("[]").split("%")[0]
    if host in _LOOPBACK_NAMES or host == "":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _no_live_network(request, monkeypatch):
    if request.node.get_closest_marker("live_network"):
        yield
        return
    attempts: list[str] = []
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _refuse(where: str):
        attempts.append(where)
        return OSError(f"live network blocked in tests (#100): {where}")

    def guarded_getaddrinfo(host, port, *args, **kwargs):
        if not _is_loopback(host):
            raise _refuse(f"getaddrinfo({host!r}, {port!r})")
        return real_getaddrinfo(host, port, *args, **kwargs)

    def _check(address):
        if isinstance(address, tuple) and not _is_loopback(address[0]):
            raise _refuse(f"connect({address[0]!r}, {address[1]!r})")

    def guarded_connect(self, address):
        _check(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        _check(address)
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
    if attempts:
        # Raised OSErrors are often swallowed by code that degrades
        # gracefully, so the test could pass; fail it here instead.
        pytest.fail(
            "test reached for the live network; patch the call or mark it "
            "@pytest.mark.live_network:\n  " + "\n  ".join(attempts),
            pytrace=False,
        )
