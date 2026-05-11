"""Unit tests for phase_write_manifest — extracted from init.quick."""

from __future__ import annotations


class _Device:
    def __init__(self, bus=None, protocol=None, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices):
        self.devices = devices
        self.cameras: list = []


def _fake_so_arm101_scan():
    return _Scan(
        [
            _Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0"),
        ]
    )


def test_writes_manifest_with_explicit_preset(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "ok"
    assert out.exists()
    text = out.read_text()
    assert "bob" in text
    assert "so-arm101" in text or "so_arm101" in text


def test_refuses_existing_file_without_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    out.write_text("old\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "exist" in result.message.lower()


def test_overwrites_with_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    # Sentinel that won't collide with the preset body (which contains words
    # like "hold", "old", etc.).
    sentinel = "ZZZ-SENTINEL-CONTENT-ZZZ"
    out.write_text(sentinel + "\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=True,
    )

    assert result.status == "ok"
    assert sentinel not in out.read_text()


def test_unknown_preset_returns_failed(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="nonexistent-preset",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "not found" in result.message.lower() or "nonexistent" in result.message
    assert not out.exists()


def _existing_manifest_with_rrn(
    path, *, rrn: str = "RRN-000000000010", record_url: str | None = None
) -> None:
    """Write a minimal valid ROBOT.md with metadata.rrn (+ optionally
    record_url) so phase_write_manifest's carry-forward path has something
    to read."""
    record_line = f"  record_url: {record_url}\n" if record_url else ""
    text = (
        "---\n"
        "rcan_version: '3.0'\n"
        "schema: https://robotmd.dev/schema/v1/robot.schema.json\n"
        "metadata:\n"
        "  robot_name: bob\n"
        "  manufacturer: bob\n"
        "  model: SO-ARM101 follower\n"
        "  version: '1.0'\n"
        "  device_id: bob\n"
        f"  rrn: {rrn}\n"
        f"{record_line}"
        "  license: Apache-2.0\n"
        "drivers: []\n"
        "---\n\n# bob\n"
    )
    path.write_text(text)


def test_force_overwrite_preserves_metadata_rrn(tmp_path):
    """init --force regenerates the manifest from scratch. The fresh
    frontmatter merger has no knowledge of an already-minted RRN — without
    this carry-forward, the operator silently loses the link between the
    new manifest and `~/.robot-md/keys/<rrn>.signing.json`. Tracked at #82."""
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    _existing_manifest_with_rrn(
        out,
        rrn="RRN-000000000010",
        record_url="https://rcan.dev/r/RRN-000000000010",
    )

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=True,
    )

    assert result.status == "ok"
    text = out.read_text()
    assert "RRN-000000000010" in text, "rrn must be carried forward on --force"
    assert "https://rcan.dev/r/RRN-000000000010" in text
    assert sorted(result.detail["carried_forward"]) == ["record_url", "rrn"]


def test_force_overwrite_carries_nothing_when_existing_lacks_rrn(tmp_path):
    """No rrn to carry forward → fresh manifest has the standard empty
    rrn placeholder; carried_forward detail is empty."""
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    _existing_manifest_with_rrn(out, rrn="")  # explicit empty
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=True,
    )
    assert result.status == "ok"
    assert result.detail["carried_forward"] == []


def test_no_force_no_carry(tmp_path):
    """When out_path doesn't exist, there's nothing to carry forward."""
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"  # does not exist
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )
    assert result.status == "ok"
    assert result.detail["carried_forward"] == []
