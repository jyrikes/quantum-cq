"""Internal multi-engine port protocols."""

from __future__ import annotations

from typing import Any, Protocol

from quantum_cq._circuits.compact import CircuitIR
from quantum_cq._engines.availability import EngineAvailability
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.measurement import MeasurementContract
from quantum_cq._engines.results import CompiledArtifact, EngineResult
from quantum_cq._engines.results import NativeExecutionResult


class EnginePortProtocol(Protocol):
    engine_id: str


class AvailabilityPort(EnginePortProtocol, Protocol):
    def availability(self) -> EngineAvailability: ...

    def is_installed(self) -> bool: ...


class CapabilitiesPort(EnginePortProtocol, Protocol):
    def capabilities(self) -> EngineCapabilities: ...


class EmitterPort(EnginePortProtocol, Protocol):
    def emit(
        self,
        circuit_ir: CircuitIR | Any,
        *,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        **options: Any,
    ) -> Any: ...


class CompilerPort(EnginePortProtocol, Protocol):
    def compile(
        self,
        emitted_circuit: Any,
        *,
        source_ir: CircuitIR | None = None,
        measurement_contract: MeasurementContract | None = None,
        capabilities: EngineCapabilities | None = None,
        availability: EngineAvailability | None = None,
        lowering_rules: tuple[str, ...] = (),
        **options: Any,
    ) -> CompiledArtifact: ...


class ExecutorPort(EnginePortProtocol, Protocol):
    def execute(
        self,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> NativeExecutionResult: ...


class ResultDecoderPort(EnginePortProtocol, Protocol):
    def decode(
        self,
        execution: NativeExecutionResult,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> EngineResult: ...


class EngineAdapterProtocol(
    AvailabilityPort,
    CapabilitiesPort,
    EmitterPort,
    CompilerPort,
    Protocol,
):
    """Backward-compatible shape for older internal tests."""

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult: ...
