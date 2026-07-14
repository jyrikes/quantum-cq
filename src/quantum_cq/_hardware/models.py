"""SDK-free hardware target domain models."""

from __future__ import annotations

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

TargetType = Literal["physical", "simulator_ideal", "simulator_noisy", "manual", "hypothetical"]


@dataclass(frozen=True)
class TargetDatum:
    status: AbsenceStatus
    value: Any = None
    unit: str | None = None
    original_value: Any = None
    original_unit: str | None = None
    reason: str = ""


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
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))


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
        object.__setattr__(self, "qubits", tuple(str(qubit) for qubit in self.qubits))
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "topology", tuple(self.topology))
        object.__setattr__(self, "structural_limits", MappingProxyType(dict(self.structural_limits)))
        if self.fingerprint is None:
            seed = f"{self.architecture_id}:{len(self.qubits)}:{','.join(item.name for item in self.instructions)}"
            object.__setattr__(self, "fingerprint", seed)

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
        object.__setattr__(self, "snapshots", tuple(self.snapshots))


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))
        if self.target is not None:
            object.__setattr__(self, "architecture", self.architecture or self.target.architecture)
            object.__setattr__(self, "snapshot", self.snapshot or self.target.snapshot)
            object.__setattr__(self, "provenance", self.provenance or self.target.provenance)


def _freeze_nested_mapping(value: Mapping[str, Mapping[str, TargetDatum]]) -> Mapping[str, Mapping[str, TargetDatum]]:
    return MappingProxyType({key: MappingProxyType(dict(nested)) for key, nested in value.items()})
