"""Neutral hardware model serialization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from quantum_cq._hardware.models import (
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetArchitecture,
    TargetDatum,
    TargetProvenance,
    TargetStateSnapshot,
    TopologyEdge,
)


SCHEMA_VERSION = "run3.hardware.v1"


def to_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        data = {
            item.name: to_serializable(getattr(value, item.name))
            for item in fields(value)
            if item.name not in {"raw"}
        }
        if value.__class__.__name__ == "ExecutionTarget":
            data["schema_version"] = SCHEMA_VERSION
        elif any(item.name == "schema_version" for item in fields(value)):
            data["schema_version"] = data.get("schema_version", SCHEMA_VERSION)
        return data
    if isinstance(value, Mapping):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset, set)):
        return [to_serializable(item) for item in value]
    return value


def execution_target_from_dict(data: dict[str, Any]) -> ExecutionTarget:
    _require_schema(data)
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
    _require_schema(data)
    payload = dict(data)
    payload["instructions"] = tuple(_instruction_from_dict(item) for item in data.get("instructions", ()))
    payload["topology"] = tuple(_edge_from_dict(item) for item in data.get("topology", ()))
    payload["structural_limits"] = _datum_mapping(data.get("structural_limits", {}))
    return TargetArchitecture(**payload)


def _instruction_from_dict(data: dict[str, Any]) -> NativeInstruction:
    payload = dict(data)
    provenance_data = payload.get("provenance")
    if provenance_data:
        payload["provenance"] = _provenance_from_dict(provenance_data)
    return NativeInstruction(**payload)


def _edge_from_dict(data: dict[str, Any]) -> TopologyEdge:
    payload = dict(data)
    payload["properties"] = _datum_mapping(data.get("properties", {}))
    return TopologyEdge(**payload)


def _snapshot_from_dict(data: dict[str, Any]) -> TargetStateSnapshot:
    _require_schema(data)
    payload = dict(data)
    for key in ("collected_at", "valid_until"):
        if payload.get(key):
            payload[key] = datetime.fromisoformat(payload[key])
    payload["queue_seconds"] = _datum_from_value(payload.get("queue_seconds", {"status": "unknown"}))
    payload["qubit_properties"] = _nested_datum_mapping(payload.get("qubit_properties", {}))
    payload["instruction_properties"] = _nested_datum_mapping(payload.get("instruction_properties", {}))
    payload["connection_properties"] = _nested_datum_mapping(payload.get("connection_properties", {}))
    return TargetStateSnapshot(**payload)


def _provenance_from_dict(data: dict[str, Any]) -> TargetProvenance:
    payload = dict(data)
    if payload.get("collected_at"):
        payload["collected_at"] = datetime.fromisoformat(payload["collected_at"])
    return TargetProvenance(**payload)


def _datum_mapping(data: Mapping[str, Any]) -> dict[str, TargetDatum]:
    return {str(key): _datum_from_value(value) for key, value in data.items()}


def _nested_datum_mapping(data: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, TargetDatum]]:
    return {str(key): _datum_mapping(value) for key, value in data.items()}


def _datum_from_value(value: Any) -> TargetDatum:
    if isinstance(value, TargetDatum):
        return value
    if isinstance(value, Mapping):
        return TargetDatum(**dict(value))
    raise TypeError(f"TargetDatum serializado invalido: {value!r}")


def _require_schema(data: Mapping[str, Any]) -> None:
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValueError(f"schema_version de hardware nao suportado: {version}")
