from qiskit import QuantumCircuit

from quantum_cq.metrics import MetricsCollector
from quantum_cq.results import AlgorithmCircuit


def test_metrics_collector_returns_basic_circuit_metrics():
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    metrics = MetricsCollector().collect(qc, extra={"encoding": "basis"})

    assert metrics["num_qubits"] == 2
    assert metrics["num_clbits"] == 2
    assert metrics["depth"] >= 2
    assert metrics["size"] >= 3
    assert metrics["count_ops"]["h"] == 1
    assert metrics["count_ops"]["cx"] == 1
    assert metrics["count_ops"]["measure"] == 2
    assert metrics["num_swap"] == 0
    assert metrics["num_mcx"] == 0
    assert metrics["num_cp"] == 0
    assert metrics["circuit_format"] == "qiskit"
    assert metrics["encoding"] == "basis"


def test_metrics_collector_accepts_algorithm_circuit_and_preserves_metadata():
    circuit = QuantumCircuit(3, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])

    algorithm_circuit = AlgorithmCircuit(
        circuit=circuit,
        algorithm_name="bernstein_vazirani",
        circuit_format="qiskit",
        metadata={
            "algorithm_name": "bernstein_vazirani",
            "family": "oracle_algorithm",
            "oracle_calls": 1,
            "operator_calls": 0,
            "primitive_calls": 0,
            "natural_encoding": "basis",
            "status": "implemented",
            "bit_order": "secret[0] -> q0 -> c0",
        },
    )

    metrics = MetricsCollector().collect(algorithm_circuit)

    assert metrics["algorithm_name"] == "bernstein_vazirani"
    assert metrics["oracle_calls"] == 1
    assert metrics["bit_order"] == "secret[0] -> q0 -> c0"
    assert metrics["num_cx"] == 1
    assert metrics["num_2q_gates"] == 1
    assert metrics["num_measurements"] == 2
