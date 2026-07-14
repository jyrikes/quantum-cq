"""Neutral hardware model serialization."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from quantum_cq._hardware.models import (
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetArchitecture,
    TargetProvenance,
    TargetStateSnapshot,
    TopologyEdge,
)


def to_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        data = {
            field.name: to_serializable(getattr(value, field.name))
            for field in fields(value)
            if field.name not in {"raw"}
        }
        if any(field.name == "schema_version" for field in fields(value)):
            data["schema_version"] = data.get("schema_version", "run3.hardware.v1")
        elif value.__class__.__name__ == "ExecutionTarget":
            data["schema_version"] = "run3.hardware.v1"
        return data
    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_serializable(item) for item in value]
    return value


def execution_target_from_dict(data: dict[str, Any]) -> ExecutionTarget:
    descriptor = ExecutionTargetDescriptor(**data["descriptor"])
    architecture = _architecture_from_dict(data["architecture"])
    snapshot_data = data.get("snapshot")
    snapshot = _snapshot_from_dict(snapshot_data) if snapshot_data else None
    provenance_data = data.get("provenance")
    provenance = _provenance_from_dict(provenance_data) if provenance_data else None
    snapshots = tuple(_snapshot_from_dict(item) for item in data.get("snapshots", ()))
    return ExecutionTarget(
        descriptor=descriptor,
        architecture=architecture,
        snapshot=snapshot,
        provenance=provenance,
        snapshots=snapshots,
    )


def _architecture_from_dict(data: dict[str, Any]) -> TargetArchitecture:
    instructions = tuple(NativeInstruction(**item) for item in data.get("instructions", ()))
    topology = tuple(TopologyEdge(**item) for item in data.get("topology", ()))
    payload = dict(data)
    payload["instructions"] = instructions
    payload["topology"] = topology
    return TargetArchitecture(**payload)


def _snapshot_from_dict(data: dict[str, Any]) -> TargetStateSnapshot:
    payload = dict(data)
    for key in ("collected_at", "valid_until"):
        if payload.get(key):
            payload[key] = datetime.fromisoformat(payload[key])
    return TargetStateSnapshot(**payload)


def _provenance_from_dict(data: dict[str, Any]) -> TargetProvenance:
    payload = dict(data)
    if payload.get("collected_at"):
        payload["collected_at"] = datetime.fromisoformat(payload["collected_at"])
    return TargetProvenance(**payload)
