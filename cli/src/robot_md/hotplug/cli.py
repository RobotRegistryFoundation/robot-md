"""Typer subcommands for the hot-plug daemon + operator review.

Two Typer apps live here:
- `app` (registered as `robot-md hotplug-daemon`): start / stop / status.
- `operator_app` (registered as `robot-md hotplug`): review / confirm /
  install-service.

`start` runs the daemon in the foreground. Backgrounding is handled by the
service manager (systemd / launchd) — see Task 22's install-service.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import typer

app = typer.Typer(help="Hot-plug daemon control")
operator_app = typer.Typer(help="Hot-plug operator review / confirm")


_PIDFILE = Path.home() / ".robot-md" / "hotplug-daemon.pid"
_QUEUE_PATH = Path.home() / ".robot-md" / "hotplug-events.jsonl"
_AUDIT_ROOT = Path.home() / ".robot-md" / "audit"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _platform_watcher_factory():
    if sys.platform == "linux":
        from robot_md.hotplug.linux import watch_devices
    elif sys.platform == "darwin":
        from robot_md.hotplug.macos import watch_devices
    else:
        from robot_md.hotplug.windows import watch_devices
    return watch_devices


@app.command("start")
def start() -> None:
    """Run the daemon in the foreground. Use the install-service installer
    (Task 22) to run this under systemd / launchd."""
    if _PIDFILE.exists():
        try:
            pid = int(_PIDFILE.read_text())
        except ValueError:
            pid = 0
        if pid and _pid_alive(pid):
            typer.echo(f"daemon already running, pid={pid}")
            raise typer.Exit(0)
        _PIDFILE.unlink(missing_ok=True)

    from robot_md.hotplug.daemon import run_daemon_with_socket
    from robot_md.hotplug.socket_listener import _DEFAULT_PATH as SOCK

    stop_event = asyncio.Event()

    def _on_sig(*_):
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    _PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    _PIDFILE.write_text(str(os.getpid()))
    try:
        rc = asyncio.run(
            run_daemon_with_socket(
                stop_event=stop_event,
                queue_path=_QUEUE_PATH,
                audit_root=_AUDIT_ROOT,
                watcher_factory=_platform_watcher_factory(),
                socket_path=SOCK,
            )
        )
        raise typer.Exit(rc)
    finally:
        _PIDFILE.unlink(missing_ok=True)


@app.command("stop")
def stop() -> None:
    if not _PIDFILE.exists():
        typer.echo("daemon not running")
        raise typer.Exit(0)
    try:
        pid = int(_PIDFILE.read_text())
    except ValueError:
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon not running (corrupt pidfile cleared)")
        raise typer.Exit(0) from None
    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon not running (stale pidfile cleared)")


@app.command("status")
def status() -> None:
    if not _PIDFILE.exists():
        typer.echo("daemon: not running")
        raise typer.Exit(0)
    try:
        pid = int(_PIDFILE.read_text())
    except ValueError:
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon: not running (corrupt pidfile cleared)")
        raise typer.Exit(0) from None
    if not _pid_alive(pid):
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon: not running (stale pidfile cleared)")
        raise typer.Exit(0)
    depth = sum(1 for _ in _QUEUE_PATH.read_text().splitlines()) if _QUEUE_PATH.exists() else 0
    typer.echo(f"daemon: running (pid={pid}); queue records: {depth}")


@operator_app.command("review")
def review() -> None:
    from robot_md.mcp.tools.hotplug_review import hotplug_review_tool

    out = hotplug_review_tool()
    pending = out["pending"]
    if not pending:
        typer.echo("no pending events")
        raise typer.Exit(0)
    typer.echo(f"{'event_id':40} {'tier':6} {'transport':12} {'path'}")
    for p in pending:
        d = p["device"]
        typer.echo(f"{p['event_id']:40} {p['tier']:6} {d['transport']:12} {d['path']}")


@operator_app.command("confirm")
def confirm(
    event_id: str,
    bind: bool = typer.Option(False, "--bind"),
    reject: bool = typer.Option(False, "--reject"),
    choice_index: int | None = typer.Option(None, "--choice"),
) -> None:
    if bind == reject:
        typer.echo("specify exactly one of --bind / --reject", err=True)
        raise typer.Exit(2)
    from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool

    out = hotplug_confirm_tool(
        event_id=event_id,
        decision="bind" if bind else "reject",
        choice_index=choice_index,
        _by="cli",
    )
    if not out.get("ok"):
        typer.echo(f"failed: {out.get('error')} {out.get('reason') or ''}", err=True)
        raise typer.Exit(1)
    typer.echo("ok")


@operator_app.command("install-service")
def install_service() -> None:
    if sys.platform == "linux":
        from robot_md.hotplug.service_installers.linux_systemd import write_unit_file

        target = Path.home() / ".config" / "systemd" / "user" / "robot-md-hotplug.service"
        write_unit_file(target=target)
        typer.echo(f"wrote {target}")
        typer.echo("enable: systemctl --user enable --now robot-md-hotplug")
    elif sys.platform == "darwin":
        from robot_md.hotplug.service_installers.macos_launchd import write_plist

        target = Path.home() / "Library" / "LaunchAgents" / "dev.robotmd.hotplug.plist"
        write_plist(target=target)
        typer.echo(f"wrote {target}")
        typer.echo(f"load: launchctl load -w {target}")
    elif sys.platform == "win32":
        typer.echo(
            "Windows installer is a follow-up; run `robot-md hotplug-daemon start` manually for now"
        )
    else:
        typer.echo(f"unsupported platform: {sys.platform}", err=True)
        raise typer.Exit(2)
