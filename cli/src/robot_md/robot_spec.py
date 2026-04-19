"""Typed frozen view of a parsed ROBOT.md — consumed by backends."""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from robot_md.parser import ParsedRobotMd


@dataclass(frozen=True)
class Intrinsic:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int
    distortion_model: str | None
    distortion_coeffs: tuple[float, ...] | None

    @classmethod
    def from_dict(cls, d: dict) -> Intrinsic:
        coeffs = d.get("distortion_coeffs")
        return cls(
            fx=float(d["fx"]),
            fy=float(d["fy"]),
            cx=float(d["cx"]),
            cy=float(d["cy"]),
            width=int(d["width"]),
            height=int(d["height"]),
            distortion_model=d.get("distortion_model"),
            distortion_coeffs=tuple(float(c) for c in coeffs) if coeffs else None,
        )


@dataclass(frozen=True)
class CameraStream:
    name: str
    intrinsic: Intrinsic | None
    baseline_m: float | None
    derived_from: tuple[str, ...] | None


@dataclass(frozen=True)
class DriverEntry:
    id: str
    protocol: str
    port: str | None
    baud_rate: int | None
    model: str | None
    count: int | None
    backend: str | None
    streams: dict[str, CameraStream]


@dataclass(frozen=True)
class SolverCamera:
    driver_id: str
    primary_stream: str
    mount: str
    extrinsic: tuple[float, ...] | None


@dataclass(frozen=True)
class MetadataBlock:
    robot_name: str
    rrn: str | None
    device_id: str | None
    manufacturer: str | None
    model: str | None
    version: str | None
    license: str | None


@dataclass(frozen=True)
class PhysicsBlock:
    type: str
    dof: int
    kinematics: tuple[dict, ...]
    solver: dict
    cameras: tuple[SolverCamera, ...]


@dataclass(frozen=True)
class SafetyBlock:
    max_joint_velocity_dps: float | None
    max_linear_velocity_ms: float | None
    payload_kg: float | None
    workspace_bounds_m: tuple[float, float, float] | None
    failsafe_behavior: str | None
    estop_software: bool
    estop_hardware: bool
    estop_response_ms: int
    hitl_gates: tuple[dict, ...]


@dataclass(frozen=True)
class BrainBlock:
    planning_provider: str | None
    planning_model: str | None
    planning_confidence_gate: float | None
    planning_timeout_ms: int
    reactive_provider: str | None
    reactive_model: str | None
    task_routing: dict[str, str]


@dataclass(frozen=True)
class RobotSpec:
    rcan_version: str
    metadata: MetadataBlock
    physics: PhysicsBlock
    drivers: tuple[DriverEntry, ...]
    safety: SafetyBlock
    capabilities: frozenset[str]
    brain: BrainBlock | None
    raw_yaml: str

    @classmethod
    def from_parsed(cls, parsed: ParsedRobotMd) -> RobotSpec:
        fm = parsed.frontmatter
        meta = fm.get("metadata", {}) or {}
        physics = fm.get("physics", {}) or {}
        solver = physics.get("solver", {}) or {}
        safety = fm.get("safety", {}) or {}
        estop = safety.get("estop", {}) or {}
        brain = fm.get("brain")

        drivers: list[DriverEntry] = []
        for d in fm.get("drivers", []) or []:
            streams: dict[str, CameraStream] = {}
            for name, s in (d.get("streams") or {}).items():
                intr = s.get("intrinsic") if isinstance(s, dict) else None
                streams[name] = CameraStream(
                    name=name,
                    intrinsic=Intrinsic.from_dict(intr) if isinstance(intr, dict) else None,
                    baseline_m=(s.get("baseline_m") if isinstance(s, dict) else None),
                    derived_from=(
                        tuple(s["derived_from"])
                        if isinstance(s, dict) and s.get("derived_from")
                        else None
                    ),
                )
            drivers.append(
                DriverEntry(
                    id=d.get("id", ""),
                    protocol=d.get("protocol", ""),
                    port=d.get("port"),
                    baud_rate=d.get("baud_rate"),
                    model=d.get("model"),
                    count=d.get("count"),
                    backend=d.get("backend"),
                    streams=streams,
                )
            )

        cams = tuple(
            SolverCamera(
                driver_id=c["driver_id"],
                primary_stream=c["primary_stream"],
                mount=c["mount"],
                extrinsic=tuple(c["extrinsic"]) if c.get("extrinsic") else None,
            )
            for c in (solver.get("cameras") or [])
        )

        workspace = safety.get("workspace_bounds_m")
        workspace_tuple: tuple[float, float, float] | None = None
        if workspace and len(workspace) == 3:
            workspace_tuple = (float(workspace[0]), float(workspace[1]), float(workspace[2]))

        brain_block: BrainBlock | None = None
        if isinstance(brain, dict):
            plan = brain.get("planning", {}) or {}
            react = brain.get("reactive", {}) or {}
            brain_block = BrainBlock(
                planning_provider=plan.get("provider"),
                planning_model=plan.get("model"),
                planning_confidence_gate=plan.get("confidence_gate"),
                planning_timeout_ms=int(plan.get("timeout_ms", 30000)),
                reactive_provider=react.get("provider"),
                reactive_model=react.get("model"),
                task_routing=dict(brain.get("task_routing") or {}),
            )

        return cls(
            rcan_version=fm.get("rcan_version", ""),
            metadata=MetadataBlock(
                robot_name=meta.get("robot_name", ""),
                rrn=meta.get("rrn"),
                device_id=meta.get("device_id"),
                manufacturer=meta.get("manufacturer"),
                model=meta.get("model"),
                version=meta.get("version"),
                license=meta.get("license"),
            ),
            physics=PhysicsBlock(
                type=physics.get("type", ""),
                dof=int(physics.get("dof", 0)),
                kinematics=tuple(physics.get("kinematics") or ()),
                solver=dict(solver),
                cameras=cams,
            ),
            drivers=tuple(drivers),
            safety=SafetyBlock(
                max_joint_velocity_dps=safety.get("max_joint_velocity_dps"),
                max_linear_velocity_ms=safety.get("max_linear_velocity_ms"),
                payload_kg=safety.get("payload_kg"),
                workspace_bounds_m=workspace_tuple,
                failsafe_behavior=safety.get("failsafe_behavior"),
                estop_software=bool(estop.get("software", True)),
                estop_hardware=bool(estop.get("hardware", False)),
                estop_response_ms=int(estop.get("response_ms", 100)),
                hitl_gates=tuple(safety.get("hitl_gates") or ()),
            ),
            capabilities=frozenset(fm.get("capabilities") or ()),
            brain=brain_block,
            raw_yaml=yaml.safe_dump(fm, sort_keys=False),
        )
