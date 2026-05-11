from typer.testing import CliRunner

from robot_md.__main__ import app


def test_install_gateway_command_exists():
    runner = CliRunner()
    result = runner.invoke(app, ["install-gateway", "--help"])
    assert result.exit_code == 0
    assert "install-gateway" in result.stdout.lower() or "scaffold" in result.stdout.lower()
