import pytest

from quantum_cq.oracles import (
    BernsteinVaziraniOracle,
    DeutschJozsaOracle,
    DeutschOracle,
    PhaseMarkedStateOracle,
)
from quantum_cq.primitives import (
    InverseQFTPrimitive,
    QFTPrimitive,
    StandardDiffuser,
    UniformSuperpositionPreparation,
)


class FakeCircuitBuilder:
    def __init__(self, num_qubits):
        self.num_qubits = num_qubits
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


def test_deutsch_oracle_cases_apply_expected_operations():
    expected = {
        1: [],
        2: [("cx", 0, 1)],
        3: [("cx", 0, 1), ("x", 1)],
        4: [("x", 1)],
    }

    for case, ops in expected.items():
        builder = FakeCircuitBuilder(2)

        DeutschOracle(case=case).apply(builder)

        assert builder.ops == ops


def test_bernstein_vazirani_oracle_uses_secret_order_directly():
    builder = FakeCircuitBuilder(5)

    BernsteinVaziraniOracle(secret="1011").apply(builder)

    assert builder.ops == [("cx", 0, 4), ("cx", 2, 4), ("cx", 3, 4)]


def test_deutsch_jozsa_oracle_constant_and_balanced_operations():
    constant = FakeCircuitBuilder(4)
    balanced = FakeCircuitBuilder(4)

    DeutschJozsaOracle(num_qubits=3, kind="constant", value=1).apply(constant)
    DeutschJozsaOracle(num_qubits=3, kind="balanced", mask="101").apply(balanced)

    assert constant.ops == [("x", 3)]
    assert balanced.ops == [("cx", 0, 3), ("cx", 2, 3)]


def test_phase_marked_state_oracle_is_planned_not_grover():
    builder = FakeCircuitBuilder(1)

    PhaseMarkedStateOracle(marked_state="1").apply(builder)

    assert ("p", pytest.approx(3.141592653589793), 0) in builder.ops


def test_uniform_superposition_applies_h_to_each_qubit():
    builder = FakeCircuitBuilder(3)

    UniformSuperpositionPreparation().apply(builder, qubits=[0, 1, 2])

    assert builder.ops == [("h", 0), ("h", 1), ("h", 2)]


def test_standard_diffuser_handles_single_qubit_without_mcx():
    builder = FakeCircuitBuilder(1)

    StandardDiffuser().apply(builder, qubits=[0])

    assert "mcx" not in [op[0] for op in builder.ops]
    assert builder.ops


def test_standard_diffuser_uses_mcx_for_multiple_qubits():
    builder = FakeCircuitBuilder(3)

    StandardDiffuser().apply(builder, qubits=[0, 1, 2])

    assert ("mcx", (0, 1), 2) in builder.ops


def test_qft_primitive_documents_swaps_and_uses_controlled_phases():
    builder = FakeCircuitBuilder(3)
    primitive = QFTPrimitive(do_swaps=True)

    primitive.apply(builder, qubits=[0, 1, 2])

    qft_doc = QFTPrimitive.__doc__ or ""
    assert "menos significativo" in qft_doc
    assert "do_swaps" in qft_doc
    assert "h" in [op[0] for op in builder.ops]
    assert "cp" in [op[0] for op in builder.ops]
    assert ("swap", 0, 2) in builder.ops


def test_qft_primitive_can_leave_order_without_swaps():
    builder = FakeCircuitBuilder(3)

    QFTPrimitive(do_swaps=False).apply(builder, qubits=[0, 1, 2])

    assert "swap" not in [op[0] for op in builder.ops]


def test_inverse_qft_primitive_uses_negative_phases():
    builder = FakeCircuitBuilder(2)

    InverseQFTPrimitive(do_swaps=False).apply(builder, qubits=[0, 1])

    assert any(op[0] == "cp" and op[1] < 0 for op in builder.ops)
