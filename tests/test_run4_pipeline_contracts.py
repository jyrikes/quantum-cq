import json

import pytest

from quantum_cq import CQ
from quantum_cq._core.results import EncodedCircuit
from quantum_cq._engines.qiskit import QiskitTranspilerPort
from quantum_cq.experiment import PipelineResult


def test_run4_legacy_pipeline_build_keeps_encoded_circuit_return():
    result = CQ.pipeline([1, 0, 1], encoding="basis").build()

    assert isinstance(result, EncodedCircuit)
    assert result.encoding_name == "basis"


def test_run4_legacy_pipeline_run_keeps_encoded_circuit_return():
    result = CQ.pipeline([0.1, 0.2], encoding="angle").run()

    assert isinstance(result, EncodedCircuit)
    assert result.encoding_name == "angle"


def test_run4_conflicting_primary_inputs_are_rejected():
    with pytest.raises(ValueError, match="entrada primaria"):
        CQ.pipeline([1, 0], equation="|psi> := H[q0] * |0>")

    custom = CQ.circuit(1)
    with pytest.raises(ValueError, match="entrada primaria"):
        CQ.pipeline(equation="|psi> := H[q0] * |0>", circuit=custom)


def test_run4_builder_terminal_methods_return_enriched_pipeline_result():
    pipeline = CQ.pipeline(equation="|psi> := H[q0] * |0>")

    transpiled = pipeline.transpile()
    assert isinstance(transpiled, PipelineResult)
    assert transpiled.logical_circuit is not None
    assert transpiled.before_transpile is not None

    compiled = pipeline.compile(engine="qiskit")
    assert isinstance(compiled, PipelineResult)
    assert compiled.compiled_artifact is not None

    pytest.importorskip("qiskit_aer")
    executed = pipeline.run_engine(engine="qiskit", shots=16)
    assert isinstance(executed, PipelineResult)
    assert executed.engine_result is not None
    assert executed.engine_result.counts


def test_run4_pipeline_result_requires_scenario_id_for_ambiguous_access():
    left = CQ.pipeline(equation="|psi> := H[q0] * |0>", scenarios=[{"scenario_id": "a"}]).transpile()
    right = CQ.pipeline(equation="|psi> := X[q0] * |0>", scenarios=[{"scenario_id": "b"}]).transpile()
    result = PipelineResult(scenario_results=left.scenario_results + right.scenario_results)

    with pytest.raises(ValueError, match="scenario_id"):
        _ = result.logical_circuit


def test_run4_pipeline_result_json_is_sdk_free_for_enriched_payload():
    result = CQ.pipeline(equation="|psi> := H[q0] * |0>").compile(engine="qiskit")

    payload = result.to_dict()
    encoded = result.to_json()
    decoded = json.loads(encoded)

    assert "scenario_results" in payload
    assert decoded["scenario_results"][0]["artifacts"]["compiled_artifact"]["engine"] == "qiskit"
    assert "QuantumCircuit(" not in encoded


def test_run4_arbitrary_to_ir_object_is_not_accepted_without_adapter():
    class Unsafe:
        def to_ir(self):
            raise AssertionError("to_ir should not be called")

    with pytest.raises(TypeError, match="input_adapter"):
        CQ.pipeline(input=Unsafe()).transpile()


def test_run4_custom_input_adapter_is_used_explicitly():
    class CustomInput:
        pass

    class Adapter:
        adapter_id = "custom"

        def supports(self, value):
            return isinstance(value, CustomInput)

        def adapt(self, value, context):
            builder = CQ.circuit(1)
            builder.x(0)
            return builder.build()

    result = CQ.pipeline(input=CustomInput(), input_adapter=Adapter()).transpile()

    assert result.logical_circuit.layers[0].operations[0].kind == "x"


def test_run4_unknown_runtime_option_is_rejected():
    with pytest.raises(ValueError, match="opcao desconhecida"):
        CQ.pipeline(equation="|psi> := H[q0] * |0>", misspelled_option=True)


def test_run4_unknown_stage_is_rejected_before_execution():
    with pytest.raises(ValueError, match="stage desconhecido"):
        CQ.pipeline(equation="|psi> := H[q0] * |0>", stages=("unknown",))


def test_run4_qiskit_native_circuit_is_restricted_to_qiskit_flow():
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(1)
    circuit.h(0)

    with pytest.raises(ValueError, match="cross-engine"):
        CQ.pipeline(circuit=circuit, engine="cirq").transpile()


def test_run4_qiskit_transpiler_port_preserves_before_after_objects():
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(1)
    circuit.h(0)

    result = QiskitTranspilerPort().transpile(circuit)

    assert result.engine == "qiskit"
    assert result.status == "completed"
    assert result.before is not circuit
    assert result.after is not circuit
    assert result.native_metadata["native_transpilation"] == "identity"
