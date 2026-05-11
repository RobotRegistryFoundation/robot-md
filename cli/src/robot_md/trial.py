"""robot-md trial: capture pick-and-place trial evidence for cert minting.

State directory layout (per trial):
    ~/.robot-md/trials/<trial_id>/
        start.json
        iter_<N>.json
        evidence.json     (written by `trial finalize`)
        frames/iter_<N>_{pre,post}_{rgb,depth}.png

Cold-install wall-clock anchor:
    ~/.robot-md-cold-install-start.txt  (operator-written before cold install)
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import secrets

import typer

trial_app = typer.Typer(help="Capture pick-and-place trial evidence for cert minting.")


@trial_app.callback()
def _trial_callback() -> None:
    """Capture pick-and-place trial evidence for cert minting."""


TRIALS_DIR = pathlib.Path.home() / ".robot-md" / "trials"
COLD_INSTALL_START_FILE = pathlib.Path.home() / ".robot-md-cold-install-start.txt"


def _utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _trial_dir(trial_id: str) -> pathlib.Path:
    return TRIALS_DIR / trial_id


def _read_cold_install_start() -> str | None:
    if not COLD_INSTALL_START_FILE.exists():
        return None
    raw = COLD_INSTALL_START_FILE.read_text().strip()
    try:
        dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return raw


@trial_app.command("start")
def start_cmd(
    property_: str = typer.Option(
        ...,
        "--property",
        help="Cert property name (e.g., bob.local/PICK-PLACE-10)",
    ),
) -> None:
    """Begin a new trial. Writes start.json with timestamps + property."""
    trial_id = "trial_" + secrets.token_hex(3)
    d = _trial_dir(trial_id)
    d.mkdir(parents=True, exist_ok=False)
    (d / "frames").mkdir()
    cold_install_start = _read_cold_install_start()
    anchor = "claude_code_first_command" if cold_install_start else "robot_md_trial_start_only"
    state = {
        "trial_id": trial_id,
        "property": property_,
        "started_at": _utcnow_iso(),
        "cold_install_start_marker": cold_install_start,
        "start_anchor": anchor,
        "iterations": [],
        "aborted_at": None,
    }
    (d / "start.json").write_text(json.dumps(state, indent=2) + "\n")
    typer.echo(f"Trial {property_} started at {state['started_at']}")
    if cold_install_start:
        typer.echo(
            f"  cold_install_start_marker: {cold_install_start}  (from {COLD_INSTALL_START_FILE})"
        )
    else:
        typer.echo(
            f"  ({COLD_INSTALL_START_FILE} not found"
            " — wall-clock anchor downgraded to post-install)"
        )
    typer.echo(f"Trial ID: {trial_id}")
    typer.echo("→ Run your Claude Code session now. After each iteration:")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --capture-pre")
    typer.echo("  → Claude does its thing →")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --capture-post-and-verdict")
    typer.echo("  → reset brick →")
    typer.echo(f"  robot-md trial iteration --trial {trial_id} --reset-confirmed")
