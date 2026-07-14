"""Engine-layer errors."""

from __future__ import annotations


class QuantumCQError(Exception):
    """Base error for quantum-cq."""


class EngineNotInstalledError(QuantumCQError, ImportError):
    """Raised when an optional engine SDK is not installed."""


class UnknownEngineError(QuantumCQError, ValueError):
    """Raised when an engine id is not registered."""


class CapabilityMismatchError(QuantumCQError):
    """Raised when an operation cannot be represented by an engine."""


class EmissionError(QuantumCQError):
    """Raised when a circuit cannot be emitted to a native SDK object."""


class CompilationError(QuantumCQError):
    """Raised when engine compilation fails."""


class ExecutionError(QuantumCQError):
    """Raised when engine execution fails."""


class ResultDecodingError(QuantumCQError):
    """Raised when a native engine result cannot be normalized."""
