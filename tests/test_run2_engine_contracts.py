import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

from quantum_cq import CQ, CompiledArtifact, MeasurementContract
from quantum_cq._circuits.compact import CircuitIR, Layer, Operation
from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.compatibility import CompatibilityEvaluator, ComponentRequirement
from quantum_cq._engines.errors import CapabilityMismatchError, ExecutionError
from quantum_cq._engines.lowering import lower_for_capabilities
from quantum_cq._engines.measurement import MeasurementMapping, prepare_ir_for_execution
from quantum_cq._engines.results import NativeExecutionResult
from quantum_cq._engines.cirq import CirqResultDecoderPort
from quantum_cq._engines.qiskit import QiskitExecutorPort
from quantum_cq.adapters import LogicalCircuitFactory


class _Port:
    def __init__(self, engine_id="fake"):
        self.engine_id = engine_id

    def availability(self):
        return SimpleNamespace(installed=True, compatible=True, available=True, reason="")

    def is_installed(self):
        return True

    def capabilities(self):
        return EngineCapabilities(
            engine=self.engine_id,
            statuses={"x": "supported"},
        )

    def emit(self, circuit_ir, **kwargs):
        return circuit_ir

    def compile(self, emitted_circuit, **kwargs):
        return CompiledArtifact(engine=self.engine_id, emitted_circuit=emitted_circuit, native_compiled=emitted_circuit)

    def execute(self, artifact, **kwargs):
        return SimpleNamespace(engine=self.engine_id, native_result=object(), metadata={})

    def decode(self, execution, artifact, **kwargs):
        return SimpleNamespace(engine=self.engine_id)


def _bell_ir(measure=True):
    builder = LogicalCircuitFactory().create(2, 2 if measure else 0)
    builder.h(0)
    builder.cx(0, 1)
    if measure:
        builder.measure(0, 0)
        builder.measure(1, 1)
    return builder.build()


def test_engine_bundle_rejects_mixed_engine_ports():
    fake = _Port("fake")
    other = _Port("other")

    with pytest.raises(ValueError, match="ports de engines diferentes"):
        EngineBundle(
            engine_id="fake",
            availability=fake,
            capabilities=fake,
            emitter=fake,
            compiler=other,
            executor=fake,
            decoder=fake,
        )


def test_facade_delegates_engine_flow_to_engine_service(monkeypatch):
    calls = []

    class FakeService:
        def emit(self, circuit_like, engine="qiskit", **options):
            calls.append((circuit_like, engine, options))
            return "native"

    monkeypatch.setattr("quantum_cq._engines.service.default_engine_service", lambda: FakeService())

    assert CQ.emit("logical", engine="fake", option=True) == "native"
    assert calls == [("logical", "fake", {"option": True})]


def test_compile_does_not_auto_measure_but_run_engine_records_auto_measurement():
    ir = _bell_ir(measure=False)

    compiled = CQ.compile(ir, engine="qiskit")
    assert compiled.measurement_contract is not None
    assert compiled.measurement_contract.effective_mappings == ()
    assert compiled.native_compiled.count_ops().get("measure", 0) == 0

    pytest.importorskip("qiskit_aer")
    result = CQ.run_engine(ir, engine="qiskit", shots=16)

    assert result.measurement_contract is not None
    assert result.measurement_contract.automatic is True
    assert result.measurement_contract.effective_mappings == (
        MeasurementMapping(0, 0, "auto"),
        MeasurementMapping(1, 1, "auto"),
    )
    assert sum(result.counts.values()) == 16


def test_qiskit_native_partial_measurement_uses_real_mappings_and_canonical_counts():
    circuit = QuantumCircuit(2, 3)
    circuit.h(0)
    circuit.measure(0, 2)

    compiled = CQ.compile(circuit, engine="qiskit")

    assert compiled.measurement_contract is not None
    assert compiled.measurement_contract.effective_mappings == (
        MeasurementMapping(0, 2, "qiskit"),
    )
    assert compiled.measurement_contract.logical_clbits == (2,)
    assert compiled.measurement_contract.canonical_bit_order == (2,)

    pytest.importorskip("qiskit_aer")
    result = CQ.run_engine(circuit, engine="qiskit", shots=32)

    assert set(result.counts).issubset({"0", "1"})
    assert sum(result.counts.values()) == 32
    assert result.normalized is True


def test_qiskit_native_measurement_handles_multiple_classical_registers():
    qreg = QuantumRegister(2, "q")
    left = ClassicalRegister(1, "left")
    right = ClassicalRegister(2, "right")
    circuit = QuantumCircuit(qreg, left, right)
    circuit.measure(qreg[1], right[1])

    compiled = CQ.compile(circuit, engine="qiskit")

    assert compiled.measurement_contract is not None
    assert compiled.measurement_contract.effective_mappings == (
        MeasurementMapping(1, 2, "qiskit"),
    )
    assert compiled.measurement_contract.canonical_bit_order == (2,)


def test_run_engine_rejects_artifact_with_incompatible_compiled_shots():
    artifact = CQ.compile(_bell_ir(), engine="qiskit", shots=4)

    with pytest.raises(CapabilityMismatchError, match="shots=4"):
        CQ.run_engine(artifact, engine="qiskit", shots=8)


def test_executor_rejects_artifact_from_another_engine_before_running_sdk():
    artifact = CompiledArtifact(engine="cirq", emitted_circuit=object(), native_compiled=object())

    with pytest.raises(ExecutionError, match="nao pode ser executado"):
        QiskitExecutorPort().execute(artifact, shots=1)


def test_result_decoder_can_be_tested_without_executor_or_sdk():
    contract = MeasurementContract(
        n_qubits=2,
        n_clbits=2,
        explicit_mappings=(MeasurementMapping(0, 0), MeasurementMapping(1, 1)),
        effective_mappings=(MeasurementMapping(0, 0), MeasurementMapping(1, 1)),
        explicit=True,
        materialized=True,
        canonical_bit_order=(1, 0),
        native_bit_order=(0, 1),
    )
    artifact = CompiledArtifact(
        engine="cirq",
        emitted_circuit=object(),
        native_compiled=object(),
        measurement_contract=contract,
    )
    raw = SimpleNamespace(
        measurements={
            "c0": [[0], [1], [0], [1]],
            "c1": [[0], [1], [0], [1]],
        }
    )
    execution = NativeExecutionResult(engine="cirq", native_result=raw, metadata={"shots": 4})

    result = CirqResultDecoderPort().decode(execution, artifact, shots=4)

    assert result.counts == {"00": 2, "11": 2}
    assert result.raw is raw
    assert result.normalized is True


def test_measurement_contract_distinguishes_partial_and_auto_measurement():
    ir = CircuitIR(
        name="partial",
        n_qubits=3,
        n_clbits=3,
        inputs=[],
        layers=[Layer([Operation("measure", qubits=(0,), clbits=(2,))])],
        outputs=[],
    )
    same, contract = prepare_ir_for_execution(ir)

    assert same is ir
    assert contract.explicit is True
    assert contract.automatic is False
    assert contract.canonical_bit_order == (2,)

    measured, auto = prepare_ir_for_execution(_bell_ir(measure=False))

    assert measured.n_clbits == 2
    assert auto.automatic is True
    assert auto.canonical_bit_order == (1, 0)


def test_lowering_validates_outputs_and_mcx_minimal_policy():
    capabilities = EngineCapabilities(
        engine="fake",
        statuses={"x": "supported", "cx": "supported", "measure": "unsupported", "ccx": "unsupported", "mcx": "unsupported"},
    )
    ir = CircuitIR(
        name="outputs",
        n_qubits=1,
        n_clbits=1,
        inputs=[],
        layers=[Layer([Operation("mcx", qubits=(0,), params={"controls": (), "target": 0})])],
        outputs=[Operation("measure", qubits=(0,), clbits=(0,))],
    )

    with pytest.raises(CapabilityMismatchError, match="measure"):
        lower_for_capabilities(ir, capabilities)

    lowered = lower_for_capabilities(
        CircuitIR(
            name="mcx",
            n_qubits=2,
            n_clbits=0,
            inputs=[],
            layers=[Layer([Operation("mcx", qubits=(0, 1), params={"controls": (0,), "target": 1})])],
            outputs=[],
        ),
        capabilities,
    )
    assert lowered.layers[0].operations[0].kind == "cx"


def test_compatibility_report_is_descriptive_and_does_not_lower():
    report = CompatibilityEvaluator().evaluate(
        component="demo",
        capabilities=EngineCapabilities(
            engine="fake",
            statuses={"x": "supported", "mcx": "lowered", "measure": "not_tested"},
        ),
        requirements=(
            ComponentRequirement("x"),
            ComponentRequirement("mcx"),
            ComponentRequirement("measure"),
        ),
    )

    assert report.status == "not_tested"
    assert "x" in report.satisfied
    assert "mcx" in report.lowerings
    assert "measure" not in report.satisfied


def test_compatibility_prefers_supported_alternative_over_lowering():
    report = CompatibilityEvaluator().evaluate(
        component="demo",
        capabilities=EngineCapabilities(
            engine="fake",
            statuses={"mcx": "lowered", "ccx": "supported"},
        ),
        requirements=(ComponentRequirement("mcx", alternatives=("ccx",)),),
    )

    assert report.status == "compatible"
    assert report.alternatives_used["mcx"] == "ccx"
    assert report.lowerings == ()


def test_run2_dtos_copy_mutable_inputs_defensively():
    statuses = {"x": "supported"}
    capabilities = EngineCapabilities(engine="fake", statuses=statuses)
    statuses["x"] = "unsupported"
    assert capabilities.status("x") == "supported"

    artifact_metadata = {"compiled": True}
    artifact = CompiledArtifact(
        engine="fake",
        emitted_circuit=object(),
        native_compiled=object(),
        metadata=artifact_metadata,
        options={"shots": 4},
        capabilities_considered={"x": "supported"},
    )
    artifact_metadata["compiled"] = False
    assert artifact.metadata["compiled"] is True
    with pytest.raises(TypeError):
        artifact.metadata["new"] = "forbidden"


def test_common_engine_dtos_do_not_import_optional_sdks():
    root = Path(__file__).resolve().parents[1]
    checked = (
        root / "src" / "quantum_cq" / "_engines" / "availability.py",
        root / "src" / "quantum_cq" / "_engines" / "measurement.py",
        root / "src" / "quantum_cq" / "_engines" / "results.py",
        root / "src" / "quantum_cq" / "_engines" / "compatibility.py",
        root / "src" / "quantum_cq" / "_core" / "components.py",
    )
    forbidden = {"pennylane", "cirq", "braket", "cudaq", "qiskit_aer", "qiskit_ibm_runtime"}

    for path in checked:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not forbidden.intersection(imports), path


def test_component_service_does_not_import_concrete_engine_registry():
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "quantum_cq" / "_core" / "components.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "quantum_cq._engines.registry" not in imports
