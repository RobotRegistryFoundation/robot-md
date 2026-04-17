"""Tests for robot_md.autodetect.

Acceptance criteria (locked in by fixture captured on a real Pi 5 + Hailo-8 +
Movidius NCS + CH340 servo bus):

1. Hailo-8 is detected as an NPU driver.
2. Movidius NCS is detected as an NPU driver.
3. CH340 USB-serial is detected as a serial-bus candidate.
4. The emitted draft validates against the v1 JSON schema.

If any of these regress, the test fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.autodetect import (
    Runtime,
    Scan,
    emit_draft,
    parse_pci,
    parse_usb,
)
from robot_md.parser import parse_file
from robot_md.validate import VALID
from robot_md.validate import validate as validate_parsed

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "autodetect"
runner = CliRunner()


@pytest.fixture
def lspci_pi5() -> str:
    return (FIXTURE_DIR / "pi5-hailo-movidius.lspci").read_text()


@pytest.fixture
def lsusb_pi5() -> str:
    return (FIXTURE_DIR / "pi5-hailo-movidius.lsusb").read_text()


def test_parse_pci_finds_hailo8(lspci_pi5):
    devs = parse_pci(lspci_pi5)
    labels = {d.driver_id for d in devs}
    assert "npu-hailo8" in labels, f"Hailo-8 missing; found: {labels}"


def test_parse_usb_finds_movidius(lsusb_pi5):
    devs = parse_usb(lsusb_pi5)
    assert any(d.driver_id == "npu-movidius-ncs2" for d in devs)


def test_parse_usb_finds_ch340_serial_bus(lsusb_pi5):
    devs = parse_usb(lsusb_pi5)
    ch340 = [d for d in devs if d.driver_id == "serial-ch340"]
    assert ch340, "CH340 not detected"
    assert ch340[0].role == "serial-bus"


def test_parse_usb_skips_unknown_vendors(lsusb_pi5):
    # Root hubs, audio codec, random USB speaker should not appear.
    devs = parse_usb(lsusb_pi5)
    for d in devs:
        assert d.role in {"npu", "camera", "serial-bus"}, (
            f"unexpected role {d.role!r} for {d.driver_id}"
        )


def test_parse_pci_line_with_rev():
    line = (
        "0001:01:00.0 Co-processor [0b40]: Hailo Technologies Ltd. "
        "Hailo-8 AI Processor [1e60:2864] (rev 01)"
    )
    devs = parse_pci(line)
    assert len(devs) == 1
    assert devs[0].vid == "1e60"
    assert devs[0].pid == "2864"
    assert devs[0].extra["pci_slot"] == "0001:01:00.0"


def test_parse_pci_ignores_malformed_lines():
    assert parse_pci("") == []
    assert parse_pci("garbage\n\n") == []
    # Valid line format but unknown VID:PID → skipped (not in DB)
    assert parse_pci("0000:00:00.0 Misc [0000]: Nobody Unknown [beef:dead]") == []


def test_emit_draft_validates_against_schema(lspci_pi5, lsusb_pi5, tmp_path):
    # Build a Scan matching what we'd get on the Pi 5.
    scan = Scan(
        devices=parse_pci(lspci_pi5) + parse_usb(lsusb_pi5),
        runtime=Runtime(
            python="3.12.0",
            platform="Linux-x86_64",
            os_release="Debian GNU/Linux 12 (bookworm)",
        ),
    )
    draft = emit_draft(scan)

    # Write to a temp file and round-trip through the normal parser+validator.
    path = tmp_path / "draft.ROBOT.md"
    path.write_text(draft)
    parsed = parse_file(path)
    result = validate_parsed(parsed)
    assert result.code == VALID, (
        f"emitted draft failed validation: {result.errors}\n--- draft ---\n{draft}"
    )


def test_emit_draft_marks_identity_fields_todo(lspci_pi5, lsusb_pi5):
    scan = Scan(devices=parse_pci(lspci_pi5) + parse_usb(lsusb_pi5))
    draft = emit_draft(scan)
    # Critical: the draft must NOT claim to know identity facts it doesn't.
    assert "CHANGE-ME" in draft
    assert "TODO" in draft
    # Must NOT auto-pick arm/wheeled — those are operator decisions.
    assert 'type: "other"' in draft


def test_emit_draft_includes_detected_devices_section(lspci_pi5, lsusb_pi5):
    scan = Scan(devices=parse_pci(lspci_pi5) + parse_usb(lsusb_pi5))
    draft = emit_draft(scan)
    assert "## Detected environment" in draft
    assert "Hailo-8" in draft
    assert "Movidius" in draft
    assert "CH340" in draft


def test_cli_autodetect_writes_to_stdout_by_default():
    result = runner.invoke(app, ["autodetect"])
    # We cannot guarantee hardware on CI; just check the command runs and
    # emits something resembling a draft.
    assert result.exit_code == 0
    assert "rcan_version" in result.stdout
    assert "TODO" in result.stdout


def test_cli_autodetect_refuses_to_overwrite(tmp_path):
    existing = tmp_path / "ROBOT.md"
    existing.write_text("already here")
    result = runner.invoke(app, ["autodetect", "--write", str(existing)])
    assert result.exit_code != 0
    # File must not have been clobbered.
    assert existing.read_text() == "already here"


def test_cli_autodetect_write_flag_creates_file(tmp_path):
    target = tmp_path / "ROBOT.md"
    result = runner.invoke(app, ["autodetect", "--write", str(target)])
    assert result.exit_code == 0, result.stdout
    assert target.exists()
    assert "rcan_version" in target.read_text()


def test_cli_help_mentions_autodetect():
    result = runner.invoke(app, ["--help"])
    assert "autodetect" in result.stdout
