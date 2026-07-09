"""Algoritmos basicos construidos via CircuitBuilderProtocol."""

from __future__ import annotations

import math
from typing import Any

from quantum_cq._circuits.compact import QC, ctrl, m, obs, sep, tgt
from quantum_cq._core.interfaces import CircuitFactoryProtocol
from quantum_cq._circuits.oracles import PhaseMarkedStateOracle
from quantum_cq._circuits.primitives import InverseQFTPrimitive, PhaseRotationUnitary, StandardDiffuser
from quantum_cq._core.results import AlgorithmCircuit


def _default_oracle_registry():
    from quantum_cq._core.handlers import default_oracle_registry

    return default_oracle_registry()


def _create_oracle(registry: Any, name: str, **kwargs: Any) -> Any:
    if hasattr(registry, "create"):
        return registry.create(name, **kwargs)

    oracle = registry.get(name)
    if kwargs:
        raise ValueError(f"Oracle registry nao aceita parametros para '{name}'")
    return oracle


def _require_circuit_factory(circuit_factory: CircuitFactoryProtocol | None) -> CircuitFactoryProtocol:
    if circuit_factory is None:
        raise ValueError("circuit_factory e obrigatoria para algoritmos")

    return circuit_factory


def _validate_secret(secret: str) -> str:
    if not secret or any(bit not in {"0", "1"} for bit in secret):
        raise ValueError("secret deve ser uma string binaria nao vazia")

    return secret


def _validate_bitstring(value: str, *, name: str) -> str:
    if not value or any(bit not in {"0", "1"} for bit in value):
        raise ValueError(f"{name} deve ser uma string binaria nao vazia")

    return value


def _validate_build_format(format: str) -> str:
    normalized = format.lower()
    if normalized not in {"qiskit", "qc", "ir"}:
        raise ValueError(f"format invalido: {format}")

    return normalized


def _phase_bits(phase: float, precision: int) -> str:
    scaled = int(round(float(phase) * (2**precision)))
    if not math.isclose(scaled / (2**precision), float(phase), abs_tol=1e-12):
        raise NotImplementedError("PhaseEstimationAlgorithm suporta apenas fases binarias exatas nesta run")

    return f"{scaled % (2**precision):0{precision}b}"


def _oracle_algorithm_metadata(
    *,
    algorithm_name: str,
    num_qubits: int,
    num_classical_bits: int,
    expected_output: Any = None,
    expected_output_type: str | None = None,
    bit_order: str,
    **extra: Any,
) -> dict[str, Any]:
    metadata = {
        "algorithm_name": algorithm_name,
        "family": "oracle_algorithm",
        "num_qubits": num_qubits,
        "num_classical_bits": num_classical_bits,
        "oracle_calls": 1,
        "operator_calls": 0,
        "primitive_calls": 0,
        "natural_encoding": "basis/phase",
        "supported_encodings": ["basis", "phase"],
        "status": "implemented",
        "bit_order": bit_order,
        **extra,
    }
    if expected_output is not None:
        metadata["expected_output"] = expected_output
    if expected_output_type is not None:
        metadata["expected_output_type"] = expected_output_type

    return metadata


class DeutschAlgorithm:
    name = "deutsch"

    def __init__(
        self,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
        oracle_registry: Any = None,
    ) -> None:
        self.circuit_factory = _require_circuit_factory(circuit_factory)
        self.oracle_registry = oracle_registry or _default_oracle_registry()
        self._case = 1

    def with_case(self, case: int) -> "DeutschAlgorithm":
        self._case = case
        return self

    def build(self, case: int | None = None, *, format: str = "qiskit") -> AlgorithmCircuit:
        selected_case = self._case if case is None else case
        circuit_format = _validate_build_format(format)
        metadata = self._metadata(selected_case)

        if circuit_format == "qc":
            return AlgorithmCircuit(
                circuit=self._build_qc(selected_case),
                algorithm_name=self.name,
                circuit_format="qc",
                metadata=metadata,
            )

        if circuit_format == "ir":
            return AlgorithmCircuit(
                circuit=self._build_qc(selected_case).to_ir(),
                algorithm_name=self.name,
                circuit_format="ir",
                metadata=metadata,
            )

        return AlgorithmCircuit(
            circuit=self._build_qiskit(selected_case),
            algorithm_name=self.name,
            circuit_format="qiskit",
            metadata=metadata,
        )

    def _metadata(self, case: int) -> dict[str, Any]:
        expected = "constant" if case in {1, 4} else "balanced"
        return _oracle_algorithm_metadata(
            algorithm_name=self.name,
            num_qubits=2,
            num_classical_bits=1,
            expected_output=expected,
            expected_output_type="classification",
            bit_order=(
                "q0 e medido em c0; output 0 indica constante e output 1 "
                "indica balanceada."
            ),
            oracle_case=case,
        )

    def _build_qiskit(self, case: int) -> Any:
        builder = self.circuit_factory.create(2, 1)
        builder.x(1)
        builder.h(0)
        builder.h(1)
        _create_oracle(self.oracle_registry, "deutsch", case=case).apply(builder)
        builder.h(0)
        builder.measure(0, 0)
        return builder.build()

    def _build_qc(self, case: int) -> QC:
        uf0 = twobit_block(case)
        return QC(
            "Deutsch",
            [
                [0, "-", "H", obs("pre_oracle"), uf0, sep("after_oracle"), "H", m(0)],
                [0, "X", "H", obs("pre_oracle"), uf0, "-", "-", "-"],
            ],
            c=1,
        )


class BernsteinVaziraniAlgorithm:
    """BV com secret[0] associado ao primeiro qubit de entrada medido."""

    name = "bernstein_vazirani"

    def __init__(
        self,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
        oracle_registry: Any = None,
    ) -> None:
        self.circuit_factory = _require_circuit_factory(circuit_factory)
        self.oracle_registry = oracle_registry or _default_oracle_registry()
        self._secret = "1"

    def with_secret(self, secret: str) -> "BernsteinVaziraniAlgorithm":
        self._secret = _validate_secret(secret)
        return self

    def build(self, secret: str | None = None, *, format: str = "qiskit") -> AlgorithmCircuit:
        circuit_format = _validate_build_format(format)
        if circuit_format != "qiskit":
            raise NotImplementedError(
                f"BernsteinVaziraniAlgorithm ainda nao implementa build(format='{circuit_format}')"
            )

        secret = _validate_secret(self._secret if secret is None else secret)
        num_inputs = len(secret)
        output_qubit = num_inputs
        builder = self.circuit_factory.create(num_inputs + 1, num_inputs)

        builder.x(output_qubit)
        builder.h(output_qubit)
        for qubit in range(num_inputs):
            builder.h(qubit)

        _create_oracle(self.oracle_registry, "bernstein_vazirani", secret=secret).apply(
            builder,
            input_qubits=list(range(num_inputs)),
            output_qubit=output_qubit,
        )

        for qubit in range(num_inputs):
            builder.h(qubit)
            builder.measure(qubit, qubit)

        metadata = _oracle_algorithm_metadata(
            algorithm_name=self.name,
            num_qubits=num_inputs + 1,
            num_classical_bits=num_inputs,
            expected_output=secret,
            expected_output_type="bitstring",
            bit_order=(
                "secret[0] corresponde a q0 medido em c0; secret[i] "
                "corresponde a qi medido em ci; expected_output segue a "
                "mesma ordem da string secret."
            ),
            expected_output_order="same_as_secret",
            secret=secret,
        )
        return AlgorithmCircuit(
            circuit=builder.build(),
            algorithm_name=self.name,
            circuit_format="qiskit",
            metadata=metadata,
        )


class DeutschJozsaAlgorithm:
    name = "deutsch_jozsa"

    def __init__(
        self,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
        oracle_registry: Any = None,
    ) -> None:
        self.circuit_factory = _require_circuit_factory(circuit_factory)
        self.oracle_registry = oracle_registry or _default_oracle_registry()
        self._num_qubits = 2
        self._kind = "constant"

    def with_num_qubits(self, num_qubits: int) -> "DeutschJozsaAlgorithm":
        if num_qubits <= 0:
            raise ValueError("num_qubits deve ser positivo")

        self._num_qubits = num_qubits
        return self

    def with_kind(self, kind: str) -> "DeutschJozsaAlgorithm":
        self._kind = kind
        return self

    def build(
        self,
        num_qubits: int | None = None,
        *,
        kind: str | None = None,
        value: int = 0,
        mask: str | None = None,
        format: str = "qiskit",
    ) -> AlgorithmCircuit:
        circuit_format = _validate_build_format(format)
        if circuit_format != "qiskit":
            raise NotImplementedError(
                f"DeutschJozsaAlgorithm ainda nao implementa build(format='{circuit_format}')"
            )

        num_qubits = self._num_qubits if num_qubits is None else num_qubits
        kind = self._kind if kind is None else kind
        if num_qubits <= 0:
            raise ValueError("num_qubits deve ser positivo")

        output_qubit = num_qubits
        builder = self.circuit_factory.create(num_qubits + 1, num_qubits)

        builder.x(output_qubit)
        builder.h(output_qubit)
        for qubit in range(num_qubits):
            builder.h(qubit)

        _create_oracle(
            self.oracle_registry,
            "deutsch_jozsa",
            num_qubits=num_qubits,
            kind=kind,
            value=value,
            mask=mask,
        ).apply(
            builder,
            input_qubits=list(range(num_qubits)),
            output_qubit=output_qubit,
        )

        for qubit in range(num_qubits):
            builder.h(qubit)
            builder.measure(qubit, qubit)

        metadata = _oracle_algorithm_metadata(
            algorithm_name=self.name,
            num_qubits=num_qubits + 1,
            num_classical_bits=num_qubits,
            expected_output_type=kind,
            bit_order=(
                "q0..q{last} sao medidos em c0..c{last}; qualquer 1 no "
                "output indica balanceada, todos 0 indicam constante."
            ).format(last=num_qubits - 1),
            oracle_kind=kind,
            oracle_mask=mask,
            oracle_value=value,
        )
        return AlgorithmCircuit(
            circuit=builder.build(),
            algorithm_name=self.name,
            circuit_format="qiskit",
            metadata=metadata,
        )


class GroverAlgorithm:
    name = "grover"

    def __init__(
        self,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
    ) -> None:
        self.circuit_factory = _require_circuit_factory(circuit_factory)
        self._marked_state = "1"
        self._iterations: int | None = None

    def with_marked_state(self, marked_state: str) -> "GroverAlgorithm":
        self._marked_state = _validate_bitstring(marked_state, name="marked_state")
        return self

    def with_iterations(self, iterations: int) -> "GroverAlgorithm":
        if iterations <= 0:
            raise ValueError("iterations deve ser positivo")

        self._iterations = iterations
        return self

    def build(
        self,
        marked_state: str | None = None,
        iterations: int | None = None,
        *,
        format: str = "qiskit",
    ) -> AlgorithmCircuit:
        circuit_format = _validate_build_format(format)
        if circuit_format != "qiskit":
            raise NotImplementedError(f"GroverAlgorithm ainda nao implementa build(format='{circuit_format}')")

        resolved_state = _validate_bitstring(
            self._marked_state if marked_state is None else marked_state,
            name="marked_state",
        )
        num_qubits = len(resolved_state)
        resolved_iterations = (
            self._iterations
            if iterations is None
            else iterations
        )
        if resolved_iterations is None:
            resolved_iterations = max(1, math.floor((math.pi / 4.0) * math.sqrt(2**num_qubits)))
        if resolved_iterations <= 0:
            raise ValueError("iterations deve ser positivo")

        builder = self.circuit_factory.create(num_qubits, num_qubits)
        for qubit in range(num_qubits):
            builder.h(qubit)

        oracle = PhaseMarkedStateOracle(marked_state=resolved_state)
        diffuser = StandardDiffuser()
        for _ in range(resolved_iterations):
            oracle.apply(builder, qubits=list(range(num_qubits)))
            diffuser.apply(builder, qubits=list(range(num_qubits)))

        for qubit in range(num_qubits):
            builder.measure(qubit, qubit)

        metadata = {
            "algorithm_name": self.name,
            "family": "search_algorithm",
            "natural_encoding": "basis/phase",
            "supported_encodings": ["basis", "phase"],
            "marked_state": resolved_state,
            "iterations": resolved_iterations,
            "oracle_calls": resolved_iterations,
            "primitive_calls": resolved_iterations,
            "operator_calls": resolved_iterations,
            "expected_output": resolved_state,
            "num_qubits": num_qubits,
            "num_classical_bits": num_qubits,
            "bit_order": "marked_state[0] corresponde a q0 medido em c0; qiskit counts aparecem invertidos.",
            "status": "implemented",
        }
        return AlgorithmCircuit(
            circuit=builder.build(),
            algorithm_name=self.name,
            circuit_format="qiskit",
            metadata=metadata,
        )


class PhaseEstimationAlgorithm:
    name = "phase_estimation"

    def __init__(
        self,
        *,
        circuit_factory: CircuitFactoryProtocol | None = None,
        alias: str | None = None,
    ) -> None:
        self.circuit_factory = _require_circuit_factory(circuit_factory)
        self.alias = alias
        self._phase = 0.5
        self._precision = 3

    def with_phase(self, phase: float) -> "PhaseEstimationAlgorithm":
        self._phase = float(phase)
        return self

    def with_precision(self, precision: int) -> "PhaseEstimationAlgorithm":
        if precision <= 0:
            raise ValueError("precision deve ser positivo")

        self._precision = precision
        return self

    def build(
        self,
        phase: float | None = None,
        precision: int | None = None,
        *,
        format: str = "qiskit",
    ) -> AlgorithmCircuit:
        circuit_format = _validate_build_format(format)
        if circuit_format != "qiskit":
            raise NotImplementedError(
                f"PhaseEstimationAlgorithm ainda nao implementa build(format='{circuit_format}')"
            )

        resolved_phase = self._phase if phase is None else float(phase)
        resolved_precision = self._precision if precision is None else precision
        if resolved_precision <= 0:
            raise ValueError("precision deve ser positivo")

        expected_bits = _phase_bits(resolved_phase, resolved_precision)
        target_qubit = resolved_precision
        builder = self.circuit_factory.create(resolved_precision + 1, resolved_precision)
        builder.x(target_qubit)
        for qubit in range(resolved_precision):
            builder.h(qubit)

        unitary = PhaseRotationUnitary(phase=resolved_phase)
        for qubit in range(resolved_precision):
            exponent = 2 ** (resolved_precision - 1 - qubit)
            unitary.power(exponent).apply_controlled(
                builder,
                control_qubit=qubit,
                target_qubit=target_qubit,
            )

        InverseQFTPrimitive().apply(builder, qubits=list(range(resolved_precision)))

        for qubit in range(resolved_precision):
            builder.measure(qubit, qubit)

        metadata = {
            "algorithm_name": self.name,
            "alias": self.alias,
            "family": "phase_estimation",
            "natural_encoding": "phase/operator",
            "supported_encodings": ["phase", "operator"],
            "unitary_name": "phase_rotation",
            "expected_phase": resolved_phase,
            "expected_output_bits": expected_bits,
            "phase_bit_order": "expected_output_bits[0] corresponde a q0/c0 e recebe U^(2^(precision-1)).",
            "classical_bit_order": "c0 recebe q0; c{i} recebe q{i}.",
            "qiskit_counts_order": "Qiskit apresenta strings como c{n-1}...c0; inverter para comparar com expected_output_bits.",
            "precision_qubits": resolved_precision,
            "target_qubits": 1,
            "num_qubits": resolved_precision + 1,
            "num_classical_bits": resolved_precision,
            "operator_calls": resolved_precision,
            "primitive_calls": 1,
            "oracle_calls": 0,
            "bit_order": "q0 e o bit menos significativo operacional; metadata documenta a ordem de leitura.",
            "status": "implemented",
        }
        return AlgorithmCircuit(
            circuit=builder.build(),
            algorithm_name=self.name,
            circuit_format="qiskit",
            metadata=metadata,
        )


def twobit_function(case: int):
    """
    Gerar uma funcao valida de dois bits como QuantumCircuit.

    Mantida para compatibilidade com as secoes legadas do notebook.
    """
    from qiskit import QuantumCircuit

    if case not in [1, 2, 3, 4]:
        raise ValueError("`case` deve ser 1, 2, 3, ou 4.")

    f = QuantumCircuit(2)
    if case in [2, 3]:
        f.cx(0, 1)
    if case in [3, 4]:
        f.x(1)
    return f


def twobit_block(case: int) -> QC:
    """
    Mesmo oraculo acima, mas escrito como subcircuito tabular compacto.

    case=1: f(x)=0      -> identidade no alvo
    case=2: f(x)=x      -> CX(q0, q1)
    case=3: f(x)=not x  -> CX(q0, q1) seguido de X(q1)
    case=4: f(x)=1      -> X(q1)
    """
    if case == 1:
        return QC("Uf_f0", [["-"], ["-"]], io=False)

    if case == 2:
        return QC("Uf_fx", [[ctrl("CX")], [tgt("CX")]], io=False)

    if case == 3:
        return QC("Uf_not_fx", [[ctrl("CX"), "-"], [tgt("CX"), "X"]], io=False)

    if case == 4:
        return QC("Uf_f1", [["-"], ["X"]], io=False)

    raise ValueError("`case` deve ser 1, 2, 3, ou 4.")


def dj_function(num_qubits):
    """Criar uma funcao aleatoria de Deutsch-Jozsa."""
    import numpy as np
    from qiskit import QuantumCircuit

    qc_dj = QuantumCircuit(num_qubits + 1, name="Uf_DJ")

    if np.random.randint(0, 2):
        qc_dj.x(num_qubits)

    if np.random.randint(0, 2):
        return qc_dj

    on_states = np.random.choice(
        range(2**num_qubits),
        2**num_qubits // 2,
        replace=False,
    )

    def add_cx(qc_dj, bit_string):
        for qubit, bit in enumerate(reversed(bit_string)):
            if bit == "1":
                qc_dj.x(qubit)
        return qc_dj

    for state in on_states:
        qc_dj = add_cx(qc_dj, f"{state:0{num_qubits}b}")
        qc_dj.mcx(list(range(num_qubits)), num_qubits)
        qc_dj = add_cx(qc_dj, f"{state:0{num_qubits}b}")

    return qc_dj


def bv_function(s):
    """Criar uma funcao de Bernstein-Vazirani a partir de uma string binaria."""
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(len(s) + 1, name="Uf_BV")

    for index, bit in enumerate(reversed(s)):
        if bit == "1":
            qc.cx(index, len(s))

    return qc
