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
from quantum_cq._engines.registry import engine_catalog, engine_capabilities, engine_names, get_engine_adapter
from quantum_cq._engines.results import CompiledArtifact, EngineResult

__all__ = [
    "CapabilityMismatchError",
    "CapabilityStatus",
    "CompilationError",
    "CompiledArtifact",
    "EmissionError",
    "EngineCapabilities",
    "EngineNotInstalledError",
    "EngineResult",
    "ExecutionError",
    "QuantumCQError",
    "ResultDecodingError",
    "UnknownEngineError",
    "engine_catalog",
    "engine_capabilities",
    "engine_names",
    "get_engine_adapter",
]
