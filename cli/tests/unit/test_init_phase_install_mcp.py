"""Package-import smoke test for init_phases."""
from __future__ import annotations


def test_phase_result_exports():
    from robot_md.init_phases import PhaseResult

    r = PhaseResult(phase="x", status="ok", message="ok", detail=None)
    assert r.phase == "x"
    assert r.status == "ok"
    assert r.message == "ok"
    assert r.detail is None


def test_phase_result_accepts_skipped_and_failed():
    from robot_md.init_phases import PhaseResult

    assert PhaseResult(phase="x", status="skipped", message="m", detail=None).status == "skipped"
    assert PhaseResult(phase="x", status="failed", message="m", detail={"e": 1}).detail == {"e": 1}
