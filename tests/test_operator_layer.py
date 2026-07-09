import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from quantum_cq import CQ
from quantum_cq.adapters import export_to_qiskit
from quantum_cq.primitives import PhaseRotationUnitary
from quantum_cq.results import NavigationCircuit, OperatorCircuit, OracleCircuit


def _assert_equal_up_to_global_phase(actual, expected, atol=1e-8):
    actual = np.asarray(actual, dtype=complex)
    expected = np.asarray(expected, dtype=complex)
    index = np.unravel_index(np.argmax(np.abs(expected)), expected.shape)
    phase = actual[index] / expected[index]
    assert np.allclose(actual, phase * expected, atol=atol)


def test_semantic_circuit_results_validate_format():
    circuit = QuantumCircuit(1)

    assert OperatorCircuit(circuit, "op").metadata["operator_name"] == "op"
    assert OracleCircuit(circuit, "oracle").metadata["oracle_name"] == "oracle"
    assert NavigationCircuit(circuit, "nav").metadata["navigation_name"] == "nav"

    with pytest.raises(ValueError, match="circuit_format"):
        OperatorCircuit(circuit, "op", circuit_format="bad")

    with pytest.raises(ValueError, match="circuit_format"):
        OracleCircuit(circuit, "oracle", circuit_format="bad")

    with pytest.raises(ValueError, match="circuit_format"):
        NavigationCircuit(circuit, "nav", circuit_format="bad")


def test_export_and_metrics_accept_operator_oracle_navigation_circuits():
    circuit = QuantumCircuit(1, 1)
    circuit.h(0)
    circuit.measure(0, 0)

    operator = OperatorCircuit(
        circuit,
        "demo_operator",
        metadata={"family": "operator", "role": "unitary", "unitary_role": "demo"},
    )
    oracle = OracleCircuit(
        circuit,
        "demo_oracle",
        metadata={"family": "oracle", "role": "phase_oracle", "oracle_type": "demo"},
    )
    navigation = NavigationCircuit(
        circuit,
        "demo_navigation",
        metadata={"family": "navigation", "role": "access_oracle", "cost_model": "explicit"},
    )

    assert export_to_qiskit(operator) is circuit
    assert export_to_qiskit(oracle) is circuit
    assert export_to_qiskit(navigation) is circuit
    assert CQ.metrics(operator)["operator_name"] == "demo_operator"
    assert CQ.metrics(oracle)["oracle_name"] == "demo_oracle"
    assert CQ.metrics(navigation)["navigation_name"] == "demo_navigation"


def test_phase_rotation_unitary_build_power_and_controlled_apply():
    unitary = PhaseRotationUnitary().with_phase(0.25)
    powered = unitary.power(2)
    built = unitary.build()

    assert isinstance(built, OperatorCircuit)
    assert built.metadata["phase"] == pytest.approx(0.25)
    assert built.metadata["powerable"] is True
    assert built.metadata["controlled"] is True
    assert powered.phase == pytest.approx(0.5)

    circuit = QuantumCircuit(2)
    builder = CQ.default_encoding_registry().get("basis").circuit_factory.create(2)
    unitary.apply_controlled(builder, control_qubit=0, target_qubit=1)
    controlled = builder.build()

    assert dict(controlled.count_ops())["cp"] == 1


def test_standard_diffuser_reflects_uniform_state_for_small_sizes():
    for num_qubits in (1, 2, 3):
        diffuser = CQ.primitive("standard_diffuser").build(num_qubits=num_qubits)
        matrix = Operator(CQ.to_qiskit(diffuser)).data
        size = 2**num_qubits
        uniform = np.ones((size, 1), dtype=complex) / np.sqrt(size)
        expected = 2 * (uniform @ uniform.conj().T) - np.eye(size)

        _assert_equal_up_to_global_phase(matrix, expected)


def test_qft_inverse_qft_is_identity_for_small_sizes():
    for num_qubits in (1, 2, 3):
        factory = CQ.default_encoding_registry().get("basis").circuit_factory
        builder = factory.create(num_qubits)
        CQ.primitive("qft").apply(builder, qubits=list(range(num_qubits)))
        CQ.primitive("inverse_qft").apply(builder, qubits=list(range(num_qubits)))

        matrix = Operator(builder.build()).data

        _assert_equal_up_to_global_phase(matrix, np.eye(2**num_qubits))


def test_qft_and_inverse_qft_build_metadata():
    qft = CQ.primitive("qft").build(num_qubits=3)
    inverse = CQ.primitive("inverse_qft").build(num_qubits=3)

    assert qft.metadata["operator_name"] == "qft"
    assert qft.metadata["unitary_role"] == "qft"
    assert qft.metadata["has_adjoint"] is True
    assert inverse.metadata["operator_name"] == "inverse_qft"
    assert inverse.metadata["unitary_role"] == "inverse_qft"
