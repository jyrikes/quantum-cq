import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from quantum_cq.algorithms import (
    BernsteinVaziraniAlgorithm,
    DeutschAlgorithm,
    DeutschJozsaAlgorithm,
    bv_function,
    dj_function,
    twobit_block,
    twobit_function,
)
from quantum_cq.compact import CircuitIR, QC
from quantum_cq.core import CQ
from quantum_cq.handlers import default_oracle_registry
from quantum_cq.results import AlgorithmCircuit


class FakeCircuitBuilder:
    def __init__(self, num_qubits, num_clbits=0):
        self.num_qubits = num_qubits
        self.num_clbits = num_clbits
        self.ops = []

    def x(self, qubit):
        self.ops.append(("x", qubit))

    def h(self, qubit):
        self.ops.append(("h", qubit))

    def rx(self, theta, qubit):
        self.ops.append(("rx", theta, qubit))

    def ry(self, theta, qubit):
        self.ops.append(("ry", theta, qubit))

    def rz(self, theta, qubit):
        self.ops.append(("rz", theta, qubit))

    def p(self, theta, qubit):
        self.ops.append(("p", theta, qubit))

    def cx(self, control, target):
        self.ops.append(("cx", control, target))

    def cz(self, control, target):
        self.ops.append(("cz", control, target))

    def cp(self, theta, control, target):
        self.ops.append(("cp", theta, control, target))

    def mcx(self, controls, target):
        self.ops.append(("mcx", tuple(controls), target))

    def swap(self, left, right):
        self.ops.append(("swap", left, right))

    def unitary(self, matrix, qubits, label=None):
        raise NotImplementedError("FakeCircuitBuilder nao suporta unitary")

    def measure(self, qubit, clbit):
        self.ops.append(("measure", qubit, clbit))

    def barrier(self):
        self.ops.append(("barrier",))

    def initialize(self, amplitudes, qubits):
        self.ops.append(("initialize", tuple(amplitudes), tuple(qubits)))

    def measure_all(self):
        self.ops.append(("measure_all",))

    def build(self):
        return self

    def depth(self):
        return len(self.ops)

    def size(self):
        return len(self.ops)

    def count_ops(self):
        counts = {}
        for op in self.ops:
            counts[op[0]] = counts.get(op[0], 0) + 1
        return counts


class FakeCircuitFactory:
    def __init__(self):
        self.builders = []

    def create(self, num_qubits, num_clbits=0):
        builder = FakeCircuitBuilder(num_qubits, num_clbits)
        self.builders.append(builder)
        return builder


def _oracle_registry():
    return default_oracle_registry()


def _dominant_state(circuit, qargs):
    without_measurements = circuit.remove_final_measurements(inplace=False)
    probabilities = Statevector.from_instruction(without_measurements).probabilities_dict(qargs=qargs)
    return str(max(probabilities, key=lambda key: probabilities[key]))


def test_deutsch_algorithm_metadata_for_constant_and_balanced_cases():
    factory = FakeCircuitFactory()
    algorithm = DeutschAlgorithm(circuit_factory=factory, oracle_registry=_oracle_registry())

    expectations = {1: "constant", 2: "balanced", 3: "balanced", 4: "constant"}
    for case, expected in expectations.items():
        result = algorithm.build(case=case)

        assert isinstance(result, AlgorithmCircuit)
        assert result.algorithm_name == "deutsch"
        assert result.circuit_format == "qiskit"
        assert result.metadata["expected_output"] == expected
        assert result.metadata["oracle_calls"] == 1
        assert result.metadata["num_qubits"] == 2
        assert result.metadata["num_classical_bits"] == 1
        assert result.metadata["natural_encoding"] == "basis/phase"
        assert result.metadata["supported_encodings"] == ["basis", "phase"]
        assert "bit_order" in result.metadata


def test_deutsch_algorithm_statevector_matches_expected_classification():
    expectations = {1: "0", 2: "1", 3: "1", 4: "0"}

    for case, expected_bit in expectations.items():
        result = CQ.algorithm("deutsch").with_case(case).build()

        assert _dominant_state(result.circuit, [0]) == expected_bit


def test_bernstein_vazirani_algorithm_documents_secret_bit_order():
    factory = FakeCircuitFactory()
    algorithm = BernsteinVaziraniAlgorithm(circuit_factory=factory, oracle_registry=_oracle_registry())

    result = algorithm.build(secret="1011")

    assert result.algorithm_name == "bernstein_vazirani"
    assert result.circuit_format == "qiskit"
    assert result.metadata["expected_output"] == "1011"
    assert result.metadata["num_qubits"] == 5
    assert result.metadata["num_classical_bits"] == 4
    assert "secret[0]" in result.metadata["bit_order"]
    assert "q0" in result.metadata["bit_order"]
    assert "c0" in result.metadata["bit_order"]
    assert result.metadata["expected_output_order"] == "same_as_secret"
    assert ("measure", 0, 0) in result.circuit.ops
    assert ("measure", 3, 3) in result.circuit.ops


def test_bernstein_vazirani_statevector_matches_secret_with_documented_order():
    secret = "1011"
    result = CQ.algorithm("bernstein_vazirani").with_secret(secret).build()

    qiskit_visual_order = _dominant_state(result.circuit, list(range(len(secret))))

    assert qiskit_visual_order[::-1] == secret
    assert result.metadata["expected_output_order"] == "same_as_secret"


def test_deutsch_jozsa_algorithm_metadata_for_constant_and_balanced():
    factory = FakeCircuitFactory()
    algorithm = DeutschJozsaAlgorithm(circuit_factory=factory, oracle_registry=_oracle_registry())

    constant = algorithm.build(num_qubits=3, kind="constant", value=1)
    balanced = algorithm.build(num_qubits=3, kind="balanced", mask="101")

    assert constant.metadata["algorithm_name"] == "deutsch_jozsa"
    assert constant.circuit_format == "qiskit"
    assert constant.metadata["expected_output_type"] == "constant"
    assert balanced.metadata["expected_output_type"] == "balanced"
    assert constant.metadata["oracle_calls"] == 1
    assert balanced.metadata["oracle_calls"] == 1
    assert "bit_order" in constant.metadata
    assert "bit_order" in balanced.metadata


def test_deutsch_jozsa_statevector_distinguishes_constant_and_balanced():
    constant = CQ.algorithm("deutsch_jozsa").with_num_qubits(3).with_kind("constant").build(value=1)
    balanced = CQ.algorithm("deutsch_jozsa").with_num_qubits(3).with_kind("balanced").build(mask="101")

    assert _dominant_state(constant.circuit, [0, 1, 2]) == "000"
    assert _dominant_state(balanced.circuit, [0, 1, 2]) != "000"


def test_cq_algorithm_returns_new_configurable_instance_each_call():
    first = CQ.algorithm("deutsch")
    second = CQ.algorithm("deutsch")

    assert first is not second
    assert first.name == "deutsch"
    assert second.name == "deutsch"


def test_cq_algorithm_fluent_state_does_not_leak_between_instances():
    a1 = CQ.algorithm("deutsch").with_case(2)
    a2 = CQ.algorithm("deutsch")

    assert a1 is not a2
    assert a1.build().metadata["oracle_case"] == 2
    assert a2.build().metadata["oracle_case"] == 1


def test_cq_available_algorithms_lists_only_implemented_defaults():
    names = CQ.available_algorithms()

    assert {"deutsch", "deutsch_jozsa", "bernstein_vazirani"}.issubset(names)
    assert "grover" in names
    assert "phase_estimation" in names
    assert "qpe" in names
    assert "shor" not in names
    assert "hhl" not in names


def test_cq_encode_defaults_to_auto_selection():
    basis = CQ.encode([1, 0, 1])
    angle = CQ.encode([0.1, 0.2])
    manual = CQ.encode([1, 0, 1], encoding="basis")

    assert basis.encoding_name == "basis"
    assert angle.encoding_name == "angle"
    assert manual.encoding_name == "basis"


def test_algorithm_fluent_api_builds_existing_algorithms():
    deutsch = CQ.algorithm("deutsch").with_case(2).build()
    bv = CQ.algorithm("bernstein_vazirani").with_secret("1011").build()
    dj = CQ.algorithm("deutsch_jozsa").with_num_qubits(3).with_kind("balanced").build()

    assert deutsch.metadata["expected_output"] == "balanced"
    assert bv.metadata["expected_output"] == "1011"
    assert dj.metadata["expected_output_type"] == "balanced"


def test_algorithm_build_formats_are_explicit():
    deutsch = CQ.algorithm("deutsch").with_case(2)

    qiskit_result = deutsch.build(format="qiskit")
    qc_result = deutsch.build(format="qc")
    ir_result = deutsch.build(format="ir")

    assert isinstance(qiskit_result.circuit, QuantumCircuit)
    assert qiskit_result.circuit_format == "qiskit"
    assert isinstance(qc_result.circuit, QC)
    assert qc_result.circuit_format == "qc"
    assert isinstance(ir_result.circuit, CircuitIR)
    assert ir_result.circuit_format == "ir"


def test_algorithm_build_reports_unimplemented_and_invalid_formats():
    with pytest.raises(NotImplementedError, match="qc"):
        CQ.algorithm("bernstein_vazirani").with_secret("1011").build(format="qc")

    with pytest.raises(NotImplementedError, match="ir"):
        CQ.algorithm("deutsch_jozsa").with_num_qubits(3).build(format="ir")

    with pytest.raises(ValueError, match="format"):
        CQ.algorithm("deutsch").build(format="invalid")


def test_legacy_algorithm_wrappers_continue_working():
    assert callable(twobit_function)
    assert callable(twobit_block)
    assert callable(dj_function)
    assert callable(bv_function)

    assert twobit_function(1).num_qubits == 2
    assert twobit_block(2).name == "Uf_fx"
    assert bv_function("101").num_qubits == 4
