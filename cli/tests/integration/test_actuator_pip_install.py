"""Integration: scaffolded actuator package pip-installs cleanly + entry-point
auto-discovers from a freshly-spawned Python process.

This test takes ~10-30s on a typical machine because it spawns `pip install`
in a clean venv. Marked `slow` so the default test run can skip it.
"""

from __future__ import annotations

import os
import subprocess
import venv

import pytest

from robot_md.actuator import scaffold_actuator_package


@pytest.mark.slow
def test_scaffolded_actuator_pip_installs_and_discovers(tmp_path):
    # Scaffold.
    pkg_root = scaffold_actuator_package("zeta-actuator", tmp_path, author="ci@example.com")

    # Build a venv to install into. This isolates from the test runner env.
    venv_dir = tmp_path / "venv"
    venv.create(venv_dir, with_pip=True)
    venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / "python"

    # Install robot-md-gateway (real PyPI dep) + the scaffolded package (editable).
    subprocess.check_call(
        [str(venv_python), "-m", "pip", "install", "--quiet", "robot-md-gateway>=0.5.0a1"],
    )
    subprocess.check_call(
        [str(venv_python), "-m", "pip", "install", "--quiet", "-e", str(pkg_root)],
    )

    # Probe entry-point discovery from the venv's interpreter.
    discover_script = (
        "from robot_md_gateway.actuator import discover_actuators; "
        "d = discover_actuators(); "
        'assert "zeta-actuator" in d, f"missing zeta-actuator in {sorted(d)}"; '
        "cls = d['zeta-actuator']; "
        "inst = cls(); "
        'assert inst.name == "zeta-actuator", inst.name'
    )
    subprocess.check_call([str(venv_python), "-c", discover_script])

    # Run the scaffolded test_actuator.py to confirm Protocol conformance.
    subprocess.check_call(
        [str(venv_python), "-m", "pip", "install", "--quiet", "pytest"],
    )
    res = subprocess.run(
        [str(venv_python), "-m", "pytest", str(pkg_root / "tests"), "-v"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"scaffolded tests failed:\n{res.stdout}\n{res.stderr}"
