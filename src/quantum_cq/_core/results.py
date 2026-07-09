"""Resultado normalizado do pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_VALID_CIRCUIT_FORMATS = {"qiskit", "qc", "ir"}


def _validate_circuit_format(owner: str, circuit_format: str) -> None:
    if circuit_format not in _VALID_CIRCUIT_FORMATS:
        raise ValueError(f"{owner}.circuit_format deve ser 'qiskit', 'qc' ou 'ir'")


@dataclass
class QuantumResult:
    counts: dict[str, int] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@dataclass
class EncodedCircuit:
    circuit: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    encoding_name: str = ""


@dataclass
class AlgorithmCircuit:
    circuit: Any
    algorithm_name: str
    circuit_format: str = "qiskit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_circuit_format("AlgorithmCircuit", self.circuit_format)

        self.metadata.setdefault("algorithm_name", self.algorithm_name)
        self.metadata.setdefault("circuit_format", self.circuit_format)
        if "bit_order" not in self.metadata:
            raise ValueError("AlgorithmCircuit.metadata deve incluir bit_order")


@dataclass
class AlgorithmSpec:
    name: str
    family: str = "algorithm"
    status: str = "planned"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperatorCircuit:
    circuit: Any
    operator_name: str
    circuit_format: str = "qiskit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_circuit_format("OperatorCircuit", self.circuit_format)
        self.metadata.setdefault("operator_name", self.operator_name)
        self.metadata.setdefault("circuit_format", self.circuit_format)
        self.metadata.setdefault("family", "operator")
        self.metadata.setdefault("role", "operator")
        self.metadata.setdefault("status", "implemented")


@dataclass
class OracleCircuit:
    circuit: Any
    oracle_name: str
    circuit_format: str = "qiskit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_circuit_format("OracleCircuit", self.circuit_format)
        self.metadata.setdefault("oracle_name", self.oracle_name)
        self.metadata.setdefault("circuit_format", self.circuit_format)
        self.metadata.setdefault("family", "oracle")
        self.metadata.setdefault("role", "oracle")
        self.metadata.setdefault("status", "implemented")


@dataclass
class NavigationCircuit:
    circuit: Any
    navigation_name: str
    circuit_format: str = "qiskit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_circuit_format("NavigationCircuit", self.circuit_format)
        self.metadata.setdefault("navigation_name", self.navigation_name)
        self.metadata.setdefault("circuit_format", self.circuit_format)
        self.metadata.setdefault("family", "navigation")
        self.metadata.setdefault("role", "navigation")
        self.metadata.setdefault("physical_qram", False)
        self.metadata.setdefault("status", "planned")


@dataclass
class CompilerResult:
    original_circuit: Any
    compiled_circuit: Any | None = None
    compiler_name: str = ""
    target_backend: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
