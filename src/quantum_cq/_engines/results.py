"""Common SDK-free engine artifacts and result wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quantum_cq._engines.measurement import MeasurementContract


@dataclass(frozen=True)
class CompiledArtifact:
    engine: str
    emitted_circuit: Any
    native_compiled: Any
    backend: Any = None
    device: Any = None
    options: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    measurement_contract: MeasurementContract | None = None
    capabilities_considered: Mapping[str, str] = field(default_factory=dict)
    lowering_rules: tuple[str, ...] = ()
    engine_version: str | None = None
    context: Any = None
    compatibility_report: Any = None
    circuit_descriptor: Any = None
    circuit_requirements: Any = None
    target_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(
            self,
            "capabilities_considered",
            MappingProxyType(dict(self.capabilities_considered)),
        )
        object.__setattr__(self, "lowering_rules", tuple(self.lowering_rules))


@dataclass(frozen=True)
class EngineResult:
    engine: str
    counts: Mapping[str, int] | None = None
    probabilities: Mapping[str, float] | None = None
    samples: Any = None
    expectation_values: tuple[float, ...] | None = None
    statevector: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Any = None
    measurement_contract: MeasurementContract | None = None
    canonical_bit_order: tuple[int, ...] = ()
    native_bit_order: tuple[int, ...] = ()
    endianness: str = "clbit-desc"
    normalized: bool = False
    context: Any = None
    execution_backend: Any = None
    execution_device: Any = None
    target_usage: str = "none"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "counts",
            None if self.counts is None else MappingProxyType(dict(self.counts)),
        )
        object.__setattr__(
            self,
            "probabilities",
            None if self.probabilities is None else MappingProxyType(dict(self.probabilities)),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "canonical_bit_order", tuple(self.canonical_bit_order))
        object.__setattr__(self, "native_bit_order", tuple(self.native_bit_order))


@dataclass(frozen=True)
class NativeExecutionResult:
    engine: str
    native_result: Any
    backend: Any = None
    device: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class NativeTranspilationResult:
    engine: str
    before: Any
    after: Any
    status: str = "completed"
    mapping_before: Mapping[str, Any] = field(default_factory=dict)
    mapping_after: Mapping[str, Any] = field(default_factory=dict)
    measurement_contract: MeasurementContract | None = None
    transformation_events: tuple[Any, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    native_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping_before", MappingProxyType(dict(self.mapping_before)))
        object.__setattr__(self, "mapping_after", MappingProxyType(dict(self.mapping_after)))
        object.__setattr__(self, "transformation_events", tuple(self.transformation_events))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "native_metadata", MappingProxyType(dict(self.native_metadata)))
