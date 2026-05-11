from unittest.mock import patch

from typer.testing import CliRunner

from robot_md.__main__ import app


def test_install_gateway_command_exists():
    runner = CliRunner()
    result = runner.invoke(app, ["install-gateway", "--help"])
    assert result.exit_code == 0
    assert "install-gateway" in result.stdout.lower() or "scaffold" in result.stdout.lower()


def test_install_gateway_default_manifest_does_not_trip_typer_readability_check():
    """Regression: default --manifest is /etc/robot-md-gateway/ROBOT.md, which
    is owned by the gateway system user and unreadable to the operator.

    Pre-v1.9.1, typer.Option(Path, ...) defaulted to readable=True and
    rejected the call before `install_gateway()` could run its idempotent
    `already_installed()` early-exit. Operators on a re-install were forced
    to skip the step manually. The option now sets readable=False so the
    function takes over path handling.
    """
    runner = CliRunner()
    # Stub install_gateway to short-circuit (don't actually try to sudo);
    # we only care that typer accepts the default path and dispatches.
    with patch("robot_md.install_gateway.install_gateway", return_value=0) as m:
        result = runner.invoke(app, ["install-gateway", "--yes"])
    assert result.exit_code == 0, f"typer rejected default path: {result.stdout}"
    m.assert_called_once()
    assert m.call_args.kwargs["manifest_path"] == "/etc/robot-md-gateway/ROBOT.md"
