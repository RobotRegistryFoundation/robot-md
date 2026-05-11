"""Per-phase functions used by `robot-md init` orchestrator.

Each phase is independently callable and returns a uniform `PhaseResult`.
Phases never raise, except `phase_write_manifest` which is allowed to
raise on truly fatal I/O errors (disk full, refuse-to-overwrite).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PhaseStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: PhaseStatus
    message: str
    detail: dict | None


from robot_md.init_phases.auto_calibrate_ready import phase_auto_calibrate_ready  # noqa: E402
from robot_md.init_phases.calibrate_extrinsic import phase_calibrate_extrinsic  # noqa: E402
from robot_md.init_phases.calibrate_sign import phase_calibrate_sign  # noqa: E402
from robot_md.init_phases.calibrate_zero import phase_calibrate_zero  # noqa: E402
from robot_md.init_phases.compliance_scaffold import phase_compliance_scaffold  # noqa: E402
from robot_md.init_phases.install_backend import phase_install_backend  # noqa: E402
from robot_md.init_phases.install_mcp import phase_install_mcp  # noqa: E402
from robot_md.init_phases.install_skill import phase_install_skill  # noqa: E402
from robot_md.init_phases.register import phase_register  # noqa: E402
from robot_md.init_phases.teach_poses import phase_teach_poses  # noqa: E402
from robot_md.init_phases.voice_setup import phase_voice_setup  # noqa: E402
from robot_md.init_phases.write_manifest import phase_write_manifest  # noqa: E402

__all__ = [
    "PhaseResult",
    "PhaseStatus",
    "phase_auto_calibrate_ready",
    "phase_calibrate_extrinsic",
    "phase_calibrate_sign",
    "phase_calibrate_zero",
    "phase_compliance_scaffold",
    "phase_install_backend",
    "phase_install_mcp",
    "phase_install_skill",
    "phase_register",
    "phase_teach_poses",
    "phase_voice_setup",
    "phase_write_manifest",
]
