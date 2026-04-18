"""Tests for robot-md doctor.

Doctor is read-only — we can run the full set of checks safely in CI as long
as we stub out the network. These tests mostly verify structural invariants
(result shape, exit-code logic, keystore permission detection) and skip the
network bucket entirely so CI stays deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md import doctor


def test_check_install_returns_results():
    results = doctor.check_install()
    assert len(results) > 0
    # Every check result has the required fields.
    for r in results:
        assert r.name
        assert r.bucket == "install"
        assert r.status in {"pass", "warn", "fail", "skip"}
        assert isinstance(r.detail, str)


def test_check_manifest_missing_file(tmp_path):
    results, fm = doctor.check_manifest(tmp_path / "nope.ROBOT.md")
    assert fm is None
    assert any(r.status == "fail" and "does not exist" in r.detail for r in results)


def test_check_manifest_bob_valid():
    bob = Path(__file__).parent.parent.parent / "examples" / "bob.ROBOT.md"
    if not bob.exists():
        pytest.skip("examples/bob.ROBOT.md not in this tree")
    results, fm = doctor.check_manifest(bob)
    assert fm is not None
    # Parse + schema checks pass for Bob.
    parse_ok = any(r.name == "manifest parse" and r.status == "pass" for r in results)
    schema_ok = any(r.name == "manifest schema" and r.status == "pass" for r in results)
    assert parse_ok
    assert schema_ok


def test_check_manifest_no_cwd_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    results, fm = doctor.check_manifest(None)
    assert fm is None
    assert any(r.status == "skip" and "no ROBOT.md" in r.detail for r in results)


def test_check_drivers_fail_on_missing_serial(tmp_path):
    fm = {"drivers": [{"id": "arm", "protocol": "feetech", "port": "/dev/nonexistent-xyz"}]}
    results = doctor.check_drivers(fm)
    assert len(results) == 1
    assert results[0].status == "fail"
    assert "does not exist" in results[0].detail


def test_check_drivers_skip_when_none():
    results = doctor.check_drivers({"drivers": []})
    assert len(results) == 1
    assert results[0].status == "skip"


def test_counts_sums_to_total():
    results = [
        doctor.CheckResult("a", "x", "pass", ""),
        doctor.CheckResult("b", "x", "pass", ""),
        doctor.CheckResult("c", "x", "warn", ""),
        doctor.CheckResult("d", "x", "fail", ""),
        doctor.CheckResult("e", "x", "skip", ""),
    ]
    c = doctor.counts(results)
    assert c == {"pass": 2, "warn": 1, "fail": 1, "skip": 1}


def test_exit_code_fail_is_nonzero():
    fail = [doctor.CheckResult("a", "x", "fail", "")]
    assert doctor.exit_code(fail, strict=False) == 1


def test_exit_code_warn_is_zero_unless_strict():
    warn = [doctor.CheckResult("a", "x", "warn", "")]
    assert doctor.exit_code(warn, strict=False) == 0
    assert doctor.exit_code(warn, strict=True) == 1


def test_exit_code_clean_is_zero():
    clean = [doctor.CheckResult("a", "x", "pass", "")]
    assert doctor.exit_code(clean, strict=False) == 0
    assert doctor.exit_code(clean, strict=True) == 0
