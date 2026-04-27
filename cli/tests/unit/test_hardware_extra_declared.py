"""SP1 Fix-A2: pyproject.toml declares a [hardware] meta-extra.

Plugin description references `pip install 'robot-md[hardware]'` —
the extra must exist or operators get a "no extras found" pip error.

Today, [hardware] is equivalent to [feetech-depthai] (covers bob's
SO-ARM101 + OAK-D). SP3 extends it to add lerobot + realsense.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore


def _load_pyproject() -> dict:
    path = Path(__file__).parent.parent.parent / "pyproject.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def test_hardware_extra_exists():
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]
    assert "hardware" in extras, (
        "pyproject.toml must declare [hardware] meta-extra. "
        f"Got: {sorted(extras.keys())}"
    )


def test_hardware_extra_includes_feetech_servo_sdk():
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]["hardware"]
    assert any("feetech-servo-sdk" in dep for dep in extras), (
        f"[hardware] must include feetech-servo-sdk. Got: {extras}"
    )


def test_hardware_extra_includes_depthai():
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]["hardware"]
    assert any("depthai" in dep for dep in extras), (
        f"[hardware] must include depthai. Got: {extras}"
    )


def test_hardware_extra_includes_pyserial():
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]["hardware"]
    assert any("pyserial" in dep for dep in extras), (
        f"[hardware] must include pyserial. Got: {extras}"
    )


def test_hardware_extra_includes_opencv():
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]["hardware"]
    assert any("opencv" in dep for dep in extras), (
        f"[hardware] must include opencv. Got: {extras}"
    )


def test_existing_extras_still_present():
    """[feetech-depthai] etc. must remain (operators may use them directly)."""
    cfg = _load_pyproject()
    extras = cfg["project"]["optional-dependencies"]
    for required in ("feetech", "vision", "feetech-depthai", "dev"):
        assert required in extras, (
            f"Existing extra [{required}] must remain. Got: {sorted(extras.keys())}"
        )
