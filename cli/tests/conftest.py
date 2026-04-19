"""Pytest fixtures shared across test files."""

from __future__ import annotations

from pathlib import Path

import pytest


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
    skip_hw = pytest.mark.skip(reason="hardware tests require --run-hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hw)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).parent.parent.parent / "examples"
