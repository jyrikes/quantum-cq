"""Adapters para circuito interno e Qiskit."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from quantum_cq._circuits.compact import CircuitIR, CompactAdapter, QC, QiskitExporter
from quantum_cq._core.results import AlgorithmCircuit, EncodedCircuit, NavigationCircuit, OperatorCircuit, OracleCircuit


def _require_qiskit() -> Any:
    try:
        from qiskit import QuantumCircuit
    except ImportError as exc:
        raise ImportError(
            "Para exportar ou construir circuitos Qiskit, instale quantum-cq[qiskit]."
        ) from exc

    return QuantumCircuit


class QiskitCircuitBuilder:
    def __init__(self, num_qubits: int, num_clbits: int = 0) -> None:
        QuantumCircuit = _require_qiskit()
        self._circuit = QuantumCircuit(num_qubits, num_clbits) if num_clbits else QuantumCircuit(num_qubits)

    def x(self, qubit: int) -> None:
        self._circuit.x(qubit)

    def h(self, qubit: int) -> None:
        self._circuit.h(qubit)

    def rx(self, theta: float, qubit: int) -> None:
        self._circuit.rx(theta, qubit)

    def ry(self, theta: float, qubit: int) -> None:
        self._circuit.ry(theta, qubit)

    def rz(self, theta: float, qubit: int) -> None:
        self._circuit.rz(theta, qubit)

    def p(self, theta: float, qubit: int) -> None:
        self._circuit.p(theta, qubit)

    def cx(self, control: int, target: int) -> None:
        self._circuit.cx(control, target)

    def cz(self, control: int, target: int) -> None:
        self._circuit.cz(control, target)

    def cp(self, theta: float, control: int, target: int) -> None:
        self._circuit.cp(theta, control, target)

    def mcx(self, controls: Sequence[int], target: int) -> None:
        self._circuit.mcx(list(controls), target)

    def swap(self, left: int, right: int) -> None:
        self._circuit.swap(left, right)

    def unitary(self, matrix, qubits: Sequence[int], label: str | None = None) -> None:
        self._circuit.unitary(matrix, list(qubits), label=label)

    def measure(self, qubit: int, clbit: int) -> None:
        self._circuit.measure(qubit, clbit)

    def barrier(self) -> None:
        self._circuit.barrier()

    def initialize(self, amplitudes: Sequence[complex], qubits: Sequence[int]) -> None:
        self._circuit.initialize(list(amplitudes), list(qubits))

    def measure_all(self) -> None:
        self._circuit.measure_all()

    def build(self) -> Any:
        return self._circuit


class QiskitCircuitFactory:
    def create(self, num_qubits: int, num_clbits: int = 0) -> QiskitCircuitBuilder:
        return QiskitCircuitBuilder(num_qubits, num_clbits)


class QiskitCircuitExporter:
    name = "qiskit"
    target_format = "qiskit"

    def export(self, circuit_like) -> Any:
        return export_to_qiskit(circuit_like)


def circuit_format_of(circuit_like) -> str:
    if isinstance(circuit_like, (AlgorithmCircuit, OperatorCircuit, OracleCircuit, NavigationCircuit)):
        return circuit_like.circuit_format

    if isinstance(circuit_like, EncodedCircuit):
        return str(circuit_like.metadata.get("circuit_format", "qiskit"))

    if isinstance(circuit_like, QC):
        return "qc"

    if isinstance(circuit_like, CircuitIR):
        return "ir"

    QuantumCircuit = _require_qiskit()
    if isinstance(circuit_like, QuantumCircuit):
        return "qiskit"

    raise TypeError(f"Formato de circuito nao suportado: {type(circuit_like).__name__}")


def export_to_qiskit(circuit_like) -> Any:
    if isinstance(
        circuit_like,
        (AlgorithmCircuit, EncodedCircuit, OperatorCircuit, OracleCircuit, NavigationCircuit),
    ):
        return export_to_qiskit(circuit_like.circuit)

    if isinstance(circuit_like, QC):
        return QiskitExporter().export(CompactAdapter().parse(circuit_like))

    if isinstance(circuit_like, CircuitIR):
        return QiskitExporter().export(circuit_like)

    QuantumCircuit = _require_qiskit()
    if isinstance(circuit_like, QuantumCircuit):
        return circuit_like

    raise TypeError(f"Formato de circuito nao suportado para Qiskit: {type(circuit_like).__name__}")


__all__ = [
    "CompactAdapter",
    "QiskitCircuitExporter",
    "QiskitCircuitBuilder",
    "QiskitCircuitFactory",
    "QiskitExporter",
    "circuit_format_of",
    "export_to_qiskit",
]
