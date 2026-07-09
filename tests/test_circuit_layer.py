import pytest
from qiskit import QuantumCircuit

from quantum_cq import CQ
from quantum_cq.adapters import export_to_qiskit
from quantum_cq.algorithms import twobit_block
from quantum_cq.compact import CircuitIR, QC, m, obs, sep
from quantum_cq.results import AlgorithmCircuit, EncodedCircuit


def _deutsch_qc():
    uf0 = twobit_block(2)
    return QC(
        "Deutsch",
        [
            [0, "-", "H", obs("pre_oracle"), uf0, sep("after_oracle"), "H", m(0)],
            [0, "X", "H", obs("pre_oracle"), uf0, "-", "-", "-"],
        ],
        c=1,
    )


def test_cq_from_qc_returns_same_validated_object():
    qc = _deutsch_qc()

    assert CQ.from_qc(qc) is qc

    with pytest.raises(TypeError, match="QC"):
        CQ.from_qc(object())


def test_cq_to_qiskit_and_export_accept_qc_and_ir():
    qc = _deutsch_qc()
    ir = qc.to_ir()

    assert isinstance(ir, CircuitIR)
    assert isinstance(CQ.to_qiskit(qc), QuantumCircuit)
    assert isinstance(CQ.to_qiskit(ir), QuantumCircuit)
    assert isinstance(CQ.export(qc, target="qiskit"), QuantumCircuit)


def test_cq_export_reports_future_targets_explicitly():
    qc = _deutsch_qc()

    assert CQ.available_exporters() == ["qiskit"]

    with pytest.raises(NotImplementedError, match="mqt"):
        CQ.export(qc, target="mqt")

    with pytest.raises(NotImplementedError, match="openqasm"):
        CQ.export(qc, target="openqasm")


def test_export_to_qiskit_rejects_unsupported_formats():
    with pytest.raises(TypeError, match="nao suportado"):
        export_to_qiskit(object())


def test_algorithm_circuit_validates_circuit_format():
    circuit = QuantumCircuit(1, 1)

    with pytest.raises(ValueError, match="circuit_format"):
        AlgorithmCircuit(
            circuit=circuit,
            algorithm_name="demo",
            circuit_format="invalid",
            metadata={"bit_order": "q0 -> c0"},
        )


def test_cq_metrics_accepts_supported_circuit_formats():
    qc = QC("Simple", [[0, "H", m(0)]], c=1)
    ir = qc.to_ir()
    qiskit_circuit = CQ.to_qiskit(qc)
    encoded = EncodedCircuit(
        circuit=qiskit_circuit,
        metadata={"encoding_name": "demo", "family": "test"},
        encoding_name="demo",
    )
    algorithm = AlgorithmCircuit(
        circuit=qiskit_circuit,
        algorithm_name="demo_algorithm",
        circuit_format="qiskit",
        metadata={
            "bit_order": "q0 -> c0",
            "family": "oracle_algorithm",
            "natural_encoding": "basis/phase",
            "oracle_calls": 1,
            "status": "implemented",
        },
    )

    assert CQ.metrics(qiskit_circuit)["circuit_format"] == "qiskit"
    assert CQ.metrics(qc)["circuit_format"] == "qc"
    assert CQ.metrics(ir)["circuit_format"] == "ir"
    assert CQ.metrics(encoded)["encoding_name"] == "demo"
    assert CQ.metrics(algorithm)["algorithm_name"] == "demo_algorithm"
    assert CQ.metrics(algorithm)["oracle_calls"] == 1


def test_cq_metrics_rejects_unsupported_formats():
    with pytest.raises(TypeError, match="nao suportado"):
        CQ.metrics(object())
