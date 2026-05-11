import subprocess
import sys
from importlib.metadata import version as pkg_version


def test_version_command_matches_installed_metadata():
    """`robot-md --version` must report the same string as pip metadata."""
    expected = pkg_version("robot-md")
    result = subprocess.run(
        [sys.executable, "-m", "robot_md", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout.strip()
    assert out.endswith(expected), (
        f"version drift: --version reported {out!r}, "
        f"pip metadata reports {expected!r}"
    )


def test_dunder_version_matches_installed_metadata():
    """`robot_md.__version__` must come from importlib.metadata, not a literal."""
    import robot_md
    assert robot_md.__version__ == pkg_version("robot-md")
