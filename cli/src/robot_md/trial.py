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
import pathlib

import typer

trial_app = typer.Typer(help="Capture pick-and-place trial evidence for cert minting.")

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
