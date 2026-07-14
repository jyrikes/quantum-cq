import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from quantum_cq import CQ, CompiledArtifact, EngineResult
from quantum_cq.adapters import LogicalCircuitFactory
from quantum_cq.navigation import AddressedMemory, AddressedMemoryEncoding


def _logical_bell_ir(measure: bool = True):
    builder = LogicalCircuitFactory().create(2, 2 if measure else 0)
    builder.h(0)
    builder.cx(0, 1)
    if measure:
        builder.measure(0, 0)
        builder.measure(1, 1)
    return builder.build()


def test_multi_engine_public_apis_and_legacy_exporters_are_distinct():
    catalog = CQ.engines()
    names = [item["engine"] for item in catalog]

    assert names == ["qiskit", "pennylane", "cirq", "braket", "cudaq"]
    assert CQ.available_exporters() == ["qiskit"]
    assert CQ.engine_capabilities("qiskit")["default"] is True
    assert CQ.engine_capabilities("qiskit")["capabilities"]["mcx"] == "supported"


def test_qiskit_emit_compile_and_run_engine_return_stable_types():
    ir = _logical_bell_ir()

    emitted = CQ.emit(ir, engine="qiskit")
    compiled = CQ.compile(ir, engine="qiskit")
    pytest.importorskip("qiskit_aer")
    result = CQ.run_engine(ir, engine="qiskit", shots=128)

    assert isinstance(emitted, QuantumCircuit)
    assert isinstance(compiled, CompiledArtifact)
    assert compiled.engine == "qiskit"
    assert compiled.emitted_circuit is not None
    assert compiled.native_compiled is not None
    assert isinstance(result, EngineResult)
    assert result.engine == "qiskit"
    assert sum(result.counts.values()) == 128
    assert set(result.counts).issubset({"00", "11"})
    assert result.raw is not None


def test_navigation_v1_can_use_logical_factory_without_qiskit_builder():
    memory = AddressedMemory([3, 1, 2, 0])
    nav = AddressedMemoryEncoding(circuit_factory=LogicalCircuitFactory()).encode(memory)

    assert nav.circuit_format == "ir"
    assert nav.metadata["access_semantics"] == "xor_load"
    assert nav.metadata["physical_qram"] is False

    matrix = np.asarray(Operator(CQ.to_qiskit(nav)).data, dtype=complex)
    assert matrix @ matrix == pytest.approx(np.eye(matrix.shape[0]))


def test_missing_optional_engine_fails_explicitly():
    if CQ.engine_capabilities("pennylane")["installed"]:
        pytest.skip("PennyLane is installed in this environment")

    with pytest.raises(ImportError, match="PennyLane"):
        CQ.emit(_logical_bell_ir(), engine="pennylane")


def test_cudaq_is_classified_honestly_without_blocking_other_engines():
    capabilities = CQ.engine_capabilities("cudaq")

    assert capabilities["engine"] == "cudaq"
    assert capabilities["capabilities"]["local_execution"] in {
        "experimental",
        "unsupported",
        "not_tested",
    }
    assert isinstance(CQ.emit(_logical_bell_ir(), engine="qiskit"), QuantumCircuit)
