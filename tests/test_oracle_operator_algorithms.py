import pytest
from qiskit.quantum_info import Statevector

from quantum_cq import CQ
from quantum_cq.oracles import PhaseMarkedStateOracle
from quantum_cq.results import AlgorithmCircuit, OracleCircuit


def _basis_index(bitstring):
    return sum(int(bit) * (2**index) for index, bit in enumerate(bitstring))


def _without_measurements(circuit):
    return circuit.remove_final_measurements(inplace=False)


def _dominant_state(circuit, qargs):
    probabilities = Statevector.from_instruction(_without_measurements(circuit)).probabilities_dict(qargs=qargs)
    return str(max(probabilities, key=lambda key: probabilities[key]))


def test_phase_marked_state_oracle_rejects_invalid_marked_state():
    with pytest.raises(ValueError, match="marked_state"):
        PhaseMarkedStateOracle(marked_state="10x")


def test_phase_marked_state_oracle_flips_only_marked_state_phase():
    for marked_state in ("1", "10", "101"):
        oracle = PhaseMarkedStateOracle(marked_state=marked_state).build()

        assert isinstance(oracle, OracleCircuit)
        assert oracle.metadata["oracle_name"] == "phase_marked_state"
        assert oracle.metadata["phase_oracle"] is True
        assert oracle.metadata["marked_state"] == marked_state
        assert "marked_state[0]" in oracle.metadata["bit_order"]

        circuit = CQ.to_qiskit(oracle)
        for value in range(2 ** len(marked_state)):
            initial = [0j] * (2 ** len(marked_state))
            initial[value] = 1
            final = Statevector(initial).evolve(circuit)
            expected_phase = -1 if value == _basis_index(marked_state) else 1

            assert final.data[value] == pytest.approx(expected_phase)


def test_grover_algorithm_builds_and_finds_marked_state():
    for marked_state, iterations in (("11", None), ("101", 2)):
        algorithm = CQ.algorithm("grover").with_marked_state(marked_state)
        if iterations is not None:
            algorithm.with_iterations(iterations)

        result = algorithm.build()
        dominant = _dominant_state(result.circuit, list(range(len(marked_state))))

        assert isinstance(result, AlgorithmCircuit)
        assert result.algorithm_name == "grover"
        assert result.circuit_format == "qiskit"
        assert result.metadata["expected_output"] == marked_state
        assert result.metadata["marked_state"] == marked_state
        assert result.metadata["oracle_calls"] == result.metadata["iterations"]
        assert dominant[::-1] == marked_state


def test_grover_build_direct_and_format_errors():
    result = CQ.algorithm("grover").build(marked_state="11", iterations=1)

    assert result.metadata["marked_state"] == "11"

    with pytest.raises(NotImplementedError, match="qc"):
        CQ.algorithm("grover").build(marked_state="11", format="qc")

    with pytest.raises(NotImplementedError, match="ir"):
        CQ.algorithm("grover").build(marked_state="11", format="ir")

    with pytest.raises(ValueError, match="format"):
        CQ.algorithm("grover").build(marked_state="11", format="bad")


@pytest.mark.parametrize(
    ("phase", "expected_bits"),
    [
        (0.5, "100"),
        (0.25, "010"),
        (0.125, "001"),
    ],
)
def test_phase_estimation_algorithm_binary_phases(phase, expected_bits):
    result = CQ.algorithm("phase_estimation").with_phase(phase).with_precision(3).build()
    dominant = _dominant_state(result.circuit, [0, 1, 2])

    assert isinstance(result, AlgorithmCircuit)
    assert result.algorithm_name == "phase_estimation"
    assert result.metadata["expected_phase"] == pytest.approx(phase)
    assert result.metadata["expected_output_bits"] == expected_bits
    assert result.metadata["phase_bit_order"]
    assert result.metadata["classical_bit_order"]
    assert result.metadata["qiskit_counts_order"]
    assert dominant[::-1] == expected_bits


def test_phase_estimation_alias_and_format_errors():
    assert CQ.algorithm("qpe").with_phase(0.25).with_precision(3).build().metadata["alias"] == "qpe"

    with pytest.raises(NotImplementedError, match="qc"):
        CQ.algorithm("phase_estimation").build(phase=0.25, precision=3, format="qc")

    with pytest.raises(NotImplementedError, match="ir"):
        CQ.algorithm("phase_estimation").build(phase=0.25, precision=3, format="ir")

    with pytest.raises(ValueError, match="format"):
        CQ.algorithm("phase_estimation").build(phase=0.25, precision=3, format="bad")
