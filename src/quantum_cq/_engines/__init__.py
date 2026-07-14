"""Lazy multi-engine layer."""

from quantum_cq._engines.capabilities import CapabilityStatus, EngineCapabilities
from quantum_cq._engines.errors import (
    CapabilityMismatchError,
    CompilationError,
    EmissionError,
    EngineNotInstalledError,
    ExecutionError,
    QuantumCQError,
    ResultDecodingError,
    UnknownEngineError,
)
from quantum_cq._engines.compatibility import (
    CompatibilityEvaluator,
    CompatibilityReport,
    ComponentRequirement,
)
from quantum_cq._engines.measurement import MeasurementContract, MeasurementMapping
from quantum_cq._engines.registry import (
    engine_catalog,
    engine_capabilities,
    engine_names,
    get_engine_adapter,
    get_engine_bundle,
)
from quantum_cq._engines.results import CompiledArtifact, EngineResult
from quantum_cq._engines.service import EngineService

__all__ = [
    "CapabilityMismatchError",
    "CapabilityStatus",
    "CompilationError",
    "CompatibilityEvaluator",
    "CompatibilityReport",
    "CompiledArtifact",
    "ComponentRequirement",
    "EmissionError",
    "EngineCapabilities",
    "EngineNotInstalledError",
    "EngineResult",
    "EngineService",
    "ExecutionError",
    "MeasurementContract",
    "MeasurementMapping",
    "QuantumCQError",
    "ResultDecodingError",
    "UnknownEngineError",
    "engine_catalog",
    "engine_capabilities",
    "engine_names",
    "get_engine_adapter",
    "get_engine_bundle",
]
