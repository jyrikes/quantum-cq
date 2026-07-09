"""Oraculos pequenos usados pelos algoritmos basicos."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from quantum_cq._core.interfaces import CircuitBuilderProtocol, CircuitFactoryProtocol
from quantum_cq._core.results import OracleCircuit


def _validate_bitstring(value: str, *, name: str) -> str:
    if not value or any(bit not in {"0", "1"} for bit in value):
        raise ValueError(f"{name} deve ser uma string binaria nao vazia")

    return value


class DeutschOracle:
    name = "deutsch"
    family = "boolean_oracle"

    def __init__(self, case: int = 1) -> None:
        if case not in {1, 2, 3, 4}:
            raise ValueError("`case` deve ser 1, 2, 3, ou 4.")

        self.case = case

    def apply(
        self,
        builder: CircuitBuilderProtocol,
        input_qubits: Sequence[int] = (0,),
        output_qubit: int = 1,
    ) -> None:
        input_qubit = int(input_qubits[0])
        if self.case in {2, 3}:
            builder.cx(input_qubit, output_qubit)
        if self.case in {3, 4}:
            builder.x(output_qubit)


class BernsteinVaziraniOracle:
    name = "bernstein_vazirani"
    family = "boolean_oracle"

    def __init__(self, secret: str = "1") -> None:
        self.secret = _validate_bitstring(secret, name="secret")

    def apply(
        self,
        builder: CircuitBuilderProtocol,
        input_qubits: Sequence[int] | None = None,
        output_qubit: int | None = None,
    ) -> None:
        input_qubits = list(range(len(self.secret))) if input_qubits is None else list(input_qubits)
        output_qubit = len(self.secret) if output_qubit is None else output_qubit

        if len(input_qubits) != len(self.secret):
            raise ValueError("input_qubits deve ter o mesmo tamanho de secret")

        # secret[0] controla o primeiro qubit medido.
        for qubit, bit in zip(input_qubits, self.secret):
            if bit == "1":
                builder.cx(qubit, output_qubit)


class DeutschJozsaOracle:
    name = "deutsch_jozsa"
    family = "boolean_oracle"

    def __init__(
        self,
        num_qubits: int = 1,
        kind: str = "constant",
        value: int = 0,
        mask: str | None = None,
    ) -> None:
        if num_qubits <= 0:
            raise ValueError("num_qubits deve ser positivo")

        if kind not in {"constant", "balanced"}:
            raise ValueError("kind deve ser 'constant' ou 'balanced'")

        if value not in {0, 1}:
            raise ValueError("value deve ser 0 ou 1")

        self.num_qubits = num_qubits
        self.kind = kind
        self.value = value
        self.mask = self._resolve_mask(mask)

    def apply(
        self,
        builder: CircuitBuilderProtocol,
        input_qubits: Sequence[int] | None = None,
        output_qubit: int | None = None,
    ) -> None:
        input_qubits = list(range(self.num_qubits)) if input_qubits is None else list(input_qubits)
        output_qubit = self.num_qubits if output_qubit is None else output_qubit

        if len(input_qubits) != self.num_qubits:
            raise ValueError("input_qubits deve ter tamanho num_qubits")

        if self.kind == "constant":
            if self.value == 1:
                builder.x(output_qubit)
            return

        for qubit, bit in zip(input_qubits, self.mask):
            if bit == "1":
                builder.cx(qubit, output_qubit)

    def _resolve_mask(self, mask: str | None) -> str:
        if self.kind == "constant":
            return "0" * self.num_qubits

        resolved = mask or ("1" + ("0" * (self.num_qubits - 1)))
        resolved = _validate_bitstring(resolved, name="mask")
        if len(resolved) != self.num_qubits:
            raise ValueError("mask deve ter tamanho num_qubits")
        if set(resolved) == {"0"}:
            raise ValueError("mask balanceada nao pode ser toda zero")

        return resolved


class PhaseMarkedStateOracle:
    name = "phase_marked_state"
    family = "oracle"

    def __init__(
        self,
        marked_state: str = "1",
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.marked_state = _validate_bitstring(marked_state, name="marked_state")
        self.circuit_factory = circuit_factory

    def build(
        self,
        marked_state: str | None = None,
        *,
        format: str = "qiskit",
    ) -> OracleCircuit:
        if format != "qiskit":
            raise NotImplementedError(f"PhaseMarkedStateOracle ainda nao implementa build(format='{format}')")

        resolved_state = self.marked_state if marked_state is None else _validate_bitstring(
            marked_state,
            name="marked_state",
        )
        builder = self._factory().create(len(resolved_state))
        self.apply(builder, marked_state=resolved_state)
        return OracleCircuit(
            circuit=builder.build(),
            oracle_name=self.name,
            circuit_format="qiskit",
            metadata=self._metadata(resolved_state),
        )

    def apply(
        self,
        builder: CircuitBuilderProtocol,
        qubits: Sequence[int] | None = None,
        marked_state: str | None = None,
    ) -> None:
        resolved_state = self.marked_state if marked_state is None else _validate_bitstring(
            marked_state,
            name="marked_state",
        )
        qubits = list(range(len(resolved_state))) if qubits is None else list(qubits)
        if len(qubits) != len(resolved_state):
            raise ValueError("qubits deve ter o mesmo tamanho de marked_state")

        for qubit, bit in zip(qubits, resolved_state):
            if bit == "0":
                builder.x(qubit)

        if len(qubits) == 1:
            builder.p(math.pi, qubits[0])
        else:
            target = qubits[-1]
            controls = qubits[:-1]
            builder.h(target)
            builder.mcx(controls, target)
            builder.h(target)

        for qubit, bit in reversed(list(zip(qubits, resolved_state))):
            if bit == "0":
                builder.x(qubit)

    def _factory(self) -> CircuitFactoryProtocol:
        if self.circuit_factory is not None:
            return self.circuit_factory

        from quantum_cq._circuits.adapters import QiskitCircuitFactory

        return QiskitCircuitFactory()

    def _metadata(self, marked_state: str) -> dict[str, Any]:
        return {
            "oracle_name": self.name,
            "family": "oracle",
            "role": "phase_oracle",
            "oracle_type": "marked_state",
            "phase_oracle": True,
            "predicate_oracle": False,
            "marked_state": marked_state,
            "num_qubits": len(marked_state),
            "status": "implemented",
            "bit_order": "marked_state[0] corresponde a q0; expected_output segue a mesma ordem.",
        }
