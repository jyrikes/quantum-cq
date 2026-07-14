"""SDK-free hardware target domain models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal


AbsenceStatus = Literal[
    "known",
    "unknown",
    "unavailable",
    "not_applicable",
    "unsupported",
    "not_loaded",
    "collection_error",
]

TargetType = Literal["physical", "simulator_ideal", "simulator_noisy", "hypothetical", "unknown"]

VALID_ABSENCE_STATUSES = {
    "known",
    "unknown",
    "unavailable",
    "not_applicable",
    "unsupported",
    "not_loaded",
    "collection_error",
}
VALID_TARGET_TYPES = {"physical", "simulator_ideal", "simulator_noisy", "hypothetical", "unknown"}


@dataclass(frozen=True)
class TargetDatum:
    status: AbsenceStatus
    value: Any = None
    unit: str | None = None
    original_value: Any = None
    original_unit: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in VALID_ABSENCE_STATUSES:
            raise ValueError(f"status de ausencia invalido: {self.status}")


@dataclass(frozen=True)
class TargetProvenance:
    provider: str
    adapter: str = ""
    engine: str | None = None
    sdk_version: str | None = None
    original_id: str | None = None
    collected_at: datetime | None = None
    transformed_fields: tuple[str, ...] = ()
    units_converted: Mapping[str, str] = field(default_factory=dict)
    omitted_fields: tuple[str, ...] = ()
    completeness: str = "unknown"
    warnings: tuple[str, ...] = ()
    source: str = "manual"

    def __post_init__(self) -> None:
        if self.collected_at is not None:
            _require_timezone(self.collected_at, "TargetProvenance.collected_at")
        object.__setattr__(self, "transformed_fields", tuple(self.transformed_fields))
        object.__setattr__(self, "units_converted", MappingProxyType(dict(self.units_converted)))
        object.__setattr__(self, "omitted_fields", tuple(self.omitted_fields))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True)
class ExecutionTargetDescriptor:
    target_id: str
    provider: str
    name: str
    target_type: TargetType
    provider_ids: Mapping[str, str] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()
    region: str | None = None
    paradigm: str = "gate_model"
    discovery_status: AbsenceStatus = "known"
    load_ref: str | None = None

    def __post_init__(self) -> None:
        if not str(self.target_id):
            raise ValueError("target_id nao pode ser vazio")
        if self.target_type not in VALID_TARGET_TYPES:
            raise ValueError(f"target_type invalido: {self.target_type}")
        if self.discovery_status not in VALID_ABSENCE_STATUSES:
            raise ValueError(f"discovery_status invalido: {self.discovery_status}")
        object.__setattr__(self, "provider_ids", MappingProxyType(dict(self.provider_ids)))
        object.__setattr__(self, "aliases", tuple(self.aliases))

    @property
    def is_physical(self) -> bool:
        return self.target_type == "physical"


@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    directed: bool = False
    operations: tuple[str, ...] = ()
    properties: Mapping[str, TargetDatum] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise ValueError("TopologyEdge requer source e target")
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "properties", _freeze_datum_mapping(self.properties))


@dataclass(frozen=True)
class NativeInstruction:
    name: str
    native_name: str | None = None
    arity: int = 1
    parameters: tuple[str, ...] = ()
    valid_qubits: tuple[str, ...] = ()
    valid_connections: tuple[tuple[str, ...], ...] = ()
    directional: bool = False
    support: str = "native"
    restrictions: Mapping[str, Any] = field(default_factory=dict)
    provenance: TargetProvenance | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("NativeInstruction requer nome")
        if int(self.arity) <= 0:
            raise ValueError("NativeInstruction requer aridade positiva")
        object.__setattr__(self, "arity", int(self.arity))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "valid_qubits", tuple(self.valid_qubits))
        object.__setattr__(self, "valid_connections", tuple(tuple(item) for item in self.valid_connections))
        object.__setattr__(self, "restrictions", MappingProxyType(dict(self.restrictions)))


@dataclass(frozen=True)
class TargetArchitecture:
    architecture_id: str
    qubits: tuple[str, ...]
    instructions: tuple[NativeInstruction, ...] = ()
    topology: tuple[TopologyEdge, ...] = ()
    connectivity: AbsenceStatus = "unknown"
    measurement: AbsenceStatus = "unknown"
    reset: AbsenceStatus = "unknown"
    classical_control: AbsenceStatus = "unknown"
    feed_forward: AbsenceStatus = "unknown"
    timing: AbsenceStatus = "unknown"
    structural_limits: Mapping[str, TargetDatum] = field(default_factory=dict)
    paradigm: str = "gate_model"
    fingerprint: str | None = None
    schema_version: str = "run3.hardware.v1"

    def __post_init__(self) -> None:
        if not str(self.architecture_id):
            raise ValueError("architecture_id nao pode ser vazio")
        if self.schema_version != "run3.hardware.v1":
            raise ValueError(f"schema_version de arquitetura nao suportado: {self.schema_version}")
        qubits = tuple(str(qubit) for qubit in self.qubits)
        if len(set(qubits)) != len(qubits):
            raise ValueError("TargetArchitecture possui qubits duplicados")
        qubit_set = set(qubits)
        instructions = tuple(self.instructions)
        topology = tuple(self.topology)
        for edge in topology:
            if edge.source not in qubit_set or edge.target not in qubit_set:
                raise ValueError("TopologyEdge aponta para qubit inexistente")
        for instruction in instructions:
            missing = set(instruction.valid_qubits) - qubit_set
            if missing:
                raise ValueError(f"NativeInstruction usa qubits inexistentes: {sorted(missing)}")
            for connection in instruction.valid_connections:
                if len(connection) != instruction.arity:
                    raise ValueError("NativeInstruction possui conexao com aridade incompatível")
                if set(connection) - qubit_set:
                    raise ValueError("NativeInstruction possui conexao com qubit inexistente")
        for status_name in (
            self.connectivity,
            self.measurement,
            self.reset,
            self.classical_control,
            self.feed_forward,
            self.timing,
        ):
            if status_name not in VALID_ABSENCE_STATUSES:
                raise ValueError(f"status de hardware invalido: {status_name}")
        object.__setattr__(self, "qubits", qubits)
        object.__setattr__(self, "instructions", instructions)
        object.__setattr__(self, "topology", topology)
        object.__setattr__(self, "structural_limits", _freeze_datum_mapping(self.structural_limits))
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", _architecture_fingerprint(self))

    @property
    def num_qubits(self) -> int:
        return len(self.qubits)


@dataclass(frozen=True)
class TargetStateSnapshot:
    snapshot_id: str
    target_id: str
    collected_at: datetime
    valid_until: datetime | None = None
    operational_status: AbsenceStatus = "unknown"
    queue_seconds: TargetDatum = field(default_factory=lambda: TargetDatum("unknown"))
    qubit_properties: Mapping[str, Mapping[str, TargetDatum]] = field(default_factory=dict)
    instruction_properties: Mapping[str, Mapping[str, TargetDatum]] = field(default_factory=dict)
    connection_properties: Mapping[str, Mapping[str, TargetDatum]] = field(default_factory=dict)
    calibration_available: AbsenceStatus = "unknown"
    schema_version: str = "run3.hardware.v1"

    def __post_init__(self) -> None:
        if self.schema_version != "run3.hardware.v1":
            raise ValueError(f"schema_version de snapshot nao suportado: {self.schema_version}")
        if not self.snapshot_id or not self.target_id:
            raise ValueError("TargetStateSnapshot requer snapshot_id e target_id")
        _require_timezone(self.collected_at, "TargetStateSnapshot.collected_at")
        if self.valid_until is not None:
            _require_timezone(self.valid_until, "TargetStateSnapshot.valid_until")
            if self.valid_until < self.collected_at:
                raise ValueError("TargetStateSnapshot.valid_until nao pode ser anterior a collected_at")
        if self.operational_status not in VALID_ABSENCE_STATUSES:
            raise ValueError(f"operational_status invalido: {self.operational_status}")
        if self.calibration_available not in VALID_ABSENCE_STATUSES:
            raise ValueError(f"calibration_available invalido: {self.calibration_available}")
        object.__setattr__(self, "queue_seconds", _normalize_datum(self.queue_seconds))
        object.__setattr__(self, "qubit_properties", _freeze_nested_mapping(self.qubit_properties))
        object.__setattr__(self, "instruction_properties", _freeze_nested_mapping(self.instruction_properties))
        object.__setattr__(self, "connection_properties", _freeze_nested_mapping(self.connection_properties))

    @property
    def stale(self) -> bool:
        return self.valid_until is not None and datetime.now(timezone.utc) > self.valid_until


@dataclass(frozen=True)
class ExecutionTarget:
    descriptor: ExecutionTargetDescriptor
    architecture: TargetArchitecture
    snapshot: TargetStateSnapshot | None = None
    provenance: TargetProvenance | None = None
    snapshots: tuple[TargetStateSnapshot, ...] = ()

    def __post_init__(self) -> None:
        if self.snapshot is not None and self.snapshot.target_id != self.descriptor.target_id:
            raise ValueError("snapshot pertence a outro target")
        snapshots = tuple(self.snapshots)
        for snapshot in snapshots:
            if snapshot.target_id != self.descriptor.target_id:
                raise ValueError("snapshot historico pertence a outro target")
        object.__setattr__(self, "snapshots", snapshots)


@dataclass(frozen=True)
class ExecutionContext:
    engine: str
    target: ExecutionTarget | None = None
    architecture: TargetArchitecture | None = None
    snapshot: TargetStateSnapshot | None = None
    measurement_policy: str = "preserve"
    shots: int | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: TargetProvenance | None = None
    target_usage: str = "analysis"
    execution_binding: str = "unbound"
    effective_backend: str | None = None
    effective_device: str | None = None

    def __post_init__(self) -> None:
        if not self.engine:
            raise ValueError("ExecutionContext requer engine")
        if self.shots is not None and int(self.shots) < 0:
            raise ValueError("ExecutionContext.shots nao pode ser negativo")
        if self.measurement_policy not in {"auto", "preserve", "all", "none"}:
            raise ValueError(f"measurement_policy invalida: {self.measurement_policy}")
        if self.target_usage not in {"none", "analysis", "compile", "execution"}:
            raise ValueError(f"target_usage invalido: {self.target_usage}")
        if self.execution_binding not in {"unbound", "executor_bound", "default_engine_device"}:
            raise ValueError(f"execution_binding invalido: {self.execution_binding}")
        _require_timezone(self.timestamp, "ExecutionContext.timestamp")
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))
        if self.target is not None:
            architecture = self.architecture or self.target.architecture
            snapshot = self.snapshot or self.target.snapshot
            if architecture.fingerprint != self.target.architecture.fingerprint:
                raise ValueError("ExecutionContext.architecture diverge do target")
            if snapshot is not None and snapshot.target_id != self.target.descriptor.target_id:
                raise ValueError("ExecutionContext.snapshot pertence a outro target")
            object.__setattr__(self, "architecture", architecture)
            object.__setattr__(self, "snapshot", snapshot)
            object.__setattr__(self, "provenance", self.provenance or self.target.provenance)


def _freeze_nested_mapping(value: Mapping[str, Mapping[str, TargetDatum]]) -> Mapping[str, Mapping[str, TargetDatum]]:
    return MappingProxyType({
        str(key): _freeze_datum_mapping(nested)
        for key, nested in value.items()
    })


def _freeze_datum_mapping(value: Mapping[str, TargetDatum | Mapping[str, Any]]) -> Mapping[str, TargetDatum]:
    return MappingProxyType({str(key): _normalize_datum(item) for key, item in value.items()})


def _normalize_datum(value: TargetDatum | Mapping[str, Any]) -> TargetDatum:
    if isinstance(value, TargetDatum):
        return value
    if isinstance(value, Mapping):
        return TargetDatum(**dict(value))
    raise TypeError(f"TargetDatum invalido: {value!r}")


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} requer timezone explicito")


def _architecture_fingerprint(architecture: TargetArchitecture) -> str:
    payload = {
        "paradigm": architecture.paradigm,
        "qubits": sorted(architecture.qubits),
        "instructions": sorted(
            ({
                "name": instruction.name,
                "native_name": instruction.native_name,
                "arity": instruction.arity,
                "parameters": sorted(instruction.parameters),
                "valid_qubits": sorted(instruction.valid_qubits),
                "valid_connections": sorted(tuple(connection) for connection in instruction.valid_connections),
                "directional": instruction.directional,
                "support": instruction.support,
                "restrictions": _plain_mapping(instruction.restrictions),
            }
            for instruction in architecture.instructions
            ),
            key=lambda item: (item["name"], item["arity"], tuple(item["valid_qubits"])),
        ),
        "topology": sorted(
            ({
                "source": edge.source,
                "target": edge.target,
                "directed": edge.directed,
                "operations": sorted(edge.operations),
                "properties": _datum_mapping(edge.properties),
            }
            for edge in architecture.topology
            ),
            key=lambda item: (item["source"], item["target"], item["directed"]),
        ),
        "connectivity": architecture.connectivity,
        "measurement": architecture.measurement,
        "reset": architecture.reset,
        "classical_control": architecture.classical_control,
        "feed_forward": architecture.feed_forward,
        "timing": architecture.timing,
        "structural_limits": _datum_mapping(architecture.structural_limits),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}


def _datum_mapping(value: Mapping[str, TargetDatum]) -> dict[str, dict[str, Any]]:
    return {
        str(key): {
            "status": datum.status,
            "value": datum.value,
            "unit": datum.unit,
            "original_value": datum.original_value,
            "original_unit": datum.original_unit,
            "reason": datum.reason,
        }
        for key, datum in sorted(value.items(), key=lambda pair: str(pair[0]))
    }
