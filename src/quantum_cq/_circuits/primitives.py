"""Primitivas pequenas de construcao de circuitos."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from quantum_cq._core.interfaces import CircuitBuilderProtocol, CircuitFactoryProtocol
from quantum_cq._core.results import OperatorCircuit


def _factory_or_default(circuit_factory: CircuitFactoryProtocol | None) -> CircuitFactoryProtocol:
    if circuit_factory is not None:
        return circuit_factory

    from quantum_cq._circuits.adapters import QiskitCircuitFactory

    return QiskitCircuitFactory()


class UniformSuperpositionPreparation:
    name = "uniform_superposition"
    family = "state_preparation"

    def __init__(self, circuit_factory: CircuitFactoryProtocol | None = None) -> None:
        self.circuit_factory = circuit_factory

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None:
        for qubit in qubits:
            builder.h(qubit)


class StandardDiffuser:
    name = "standard_diffuser"
    family = "operator"

    def __init__(self, circuit_factory: CircuitFactoryProtocol | None = None) -> None:
        self.circuit_factory = circuit_factory

    def build(self, num_qubits: int, *, format: str = "qiskit") -> OperatorCircuit:
        if format not in {"qiskit", "ir"}:
            raise NotImplementedError(f"StandardDiffuser ainda nao implementa build(format='{format}')")
        if num_qubits <= 0:
            raise ValueError("num_qubits deve ser positivo")

        builder = _factory_or_default(self.circuit_factory).create(num_qubits)
        self.apply(builder, qubits=list(range(num_qubits)))
        circuit_format = str(getattr(builder, "target_format", format))
        return OperatorCircuit(
            circuit=builder.build(),
            operator_name=self.name,
            circuit_format=circuit_format,
            metadata={
                "operator_name": self.name,
                "family": "operator",
                "role": "diffuser",
                "unitary_role": "reflection",
                "num_qubits": num_qubits,
                "status": "implemented",
            },
        )

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None:
        qubits = list(qubits)
        if not qubits:
            raise ValueError("StandardDiffuser requer ao menos um qubit")

        if len(qubits) == 1:
            qubit = qubits[0]
            builder.h(qubit)
            builder.x(qubit)
            builder.p(math.pi, qubit)
            builder.x(qubit)
            builder.h(qubit)
            return

        target = qubits[-1]
        controls = qubits[:-1]

        for qubit in qubits:
            builder.h(qubit)
            builder.x(qubit)

        builder.h(target)
        builder.mcx(controls, target)
        builder.h(target)

        for qubit in qubits:
            builder.x(qubit)
            builder.h(qubit)


class QFTPrimitive:
    """QFT com qubits em ordem little-endian.

    qubits[0] e tratado como o menos significativo. Quando do_swaps=True,
    swaps finais invertem a ordem dos qubits; quando False, a ordem natural
    do circuito e preservada sem swaps finais.
    """

    name = "qft"
    family = "fourier_transform"

    def __init__(
        self,
        do_swaps: bool = True,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.do_swaps = do_swaps
        self.circuit_factory = circuit_factory

    def build(self, num_qubits: int, *, format: str = "qiskit") -> OperatorCircuit:
        if format != "qiskit":
            raise NotImplementedError(f"QFTPrimitive ainda nao implementa build(format='{format}')")
        if num_qubits <= 0:
            raise ValueError("num_qubits deve ser positivo")

        builder = _factory_or_default(self.circuit_factory).create(num_qubits)
        self.apply(builder, qubits=list(range(num_qubits)))
        return OperatorCircuit(
            circuit=builder.build(),
            operator_name=self.name,
            circuit_format="qiskit",
            metadata=self._metadata(num_qubits),
        )

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None:
        qubits = list(qubits)
        for target_index, target in enumerate(qubits):
            builder.h(target)
            for control_index in range(target_index + 1, len(qubits)):
                control = qubits[control_index]
                theta = math.pi / (2 ** (control_index - target_index))
                builder.cp(theta, control, target)

        if self.do_swaps:
            for index in range(len(qubits) // 2):
                builder.swap(qubits[index], qubits[-index - 1])

    def _metadata(self, num_qubits: int) -> dict[str, Any]:
        return {
            "operator_name": self.name,
            "family": "operator",
            "role": "fourier_transform",
            "unitary_role": "qft",
            "num_qubits": num_qubits,
            "has_adjoint": True,
            "do_swaps": self.do_swaps,
            "bit_order": "qubits[0] e o menos significativo; do_swaps controla swaps finais.",
            "status": "implemented",
        }


class InverseQFTPrimitive(QFTPrimitive):
    name = "inverse_qft"

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None:
        qubits = list(qubits)

        if self.do_swaps:
            for index in range(len(qubits) // 2):
                builder.swap(qubits[index], qubits[-index - 1])

        for target_index in reversed(range(len(qubits))):
            target = qubits[target_index]
            for control_index in reversed(range(target_index + 1, len(qubits))):
                control = qubits[control_index]
                theta = -math.pi / (2 ** (control_index - target_index))
                builder.cp(theta, control, target)
            builder.h(target)

    def _metadata(self, num_qubits: int) -> dict[str, Any]:
        metadata = super()._metadata(num_qubits)
        metadata["operator_name"] = self.name
        metadata["unitary_role"] = "inverse_qft"
        return metadata


class PhaseRotationUnitary:
    name = "phase_rotation"
    family = "operator"
    num_qubits = 1

    def __init__(
        self,
        phase: float = 0.0,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.phase = float(phase)
        self.circuit_factory = circuit_factory

    def with_phase(self, phase: float) -> "PhaseRotationUnitary":
        self.phase = float(phase)
        return self

    def build(self, *, format: str = "qiskit") -> OperatorCircuit:
        if format not in {"qiskit", "ir"}:
            raise NotImplementedError(f"PhaseRotationUnitary ainda nao implementa build(format='{format}')")

        builder = _factory_or_default(self.circuit_factory).create(1)
        self.apply(builder, target_qubit=0)
        circuit_format = str(getattr(builder, "target_format", format))
        return OperatorCircuit(
            circuit=builder.build(),
            operator_name=self.name,
            circuit_format=circuit_format,
            metadata=self._metadata(),
        )

    def apply(self, builder: CircuitBuilderProtocol, target_qubit: int = 0) -> None:
        builder.p(2 * math.pi * self.phase, target_qubit)

    def apply_controlled(
        self,
        builder: CircuitBuilderProtocol,
        *,
        control_qubit: int,
        target_qubit: int,
    ) -> None:
        builder.cp(2 * math.pi * self.phase, control_qubit, target_qubit)

    def power(self, exponent: int) -> "PhaseRotationUnitary":
        if exponent < 0:
            raise ValueError("exponent deve ser nao negativo")

        return PhaseRotationUnitary(
            phase=self.phase * exponent,
            circuit_factory=self.circuit_factory,
        )

    def _metadata(self) -> dict[str, Any]:
        return {
            "operator_name": self.name,
            "family": "operator",
            "role": "unitary",
            "unitary_role": "phase_rotation",
            "phase": self.phase,
            "num_qubits": 1,
            "powerable": True,
            "controlled": True,
            "has_adjoint": True,
            "status": "implemented",
        }
