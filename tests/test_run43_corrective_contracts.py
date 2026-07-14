import pytest

from quantum_cq import CQ


def test_run43_stop_after_unknown_is_rejected_without_stages():
    with pytest.raises(ValueError, match="stop_after desconhecido"):
        CQ.pipeline(equation="|psi> := H[q0] * |0>", stop_after="unknown_stage").transpile()


def test_run43_scenario_status_reflects_insufficient_information():
    target = CQ.manual_target(
        target_id="timing-unknown",
        qubits=1,
        operations=[{"name": "h", "arity": 1}],
        target_type="simulator_ideal",
    )

    result = CQ.pipeline(
        equation="|psi> := H[q0] * |0>",
        stages=("mqt_lower", "scheduling"),
        scheduling="asap",
        target=target,
    ).transpile()

    scenario = result.scenario_results[0]
    assert scenario.status == "insufficient_information"
    assert any(stage.stage_id == "scheduling" and stage.status == "insufficient_information" for stage in scenario.stage_results)


def test_run43_stop_after_valid_completion_keeps_skipped_stages_visible():
    result = CQ.pipeline(
        equation="|psi> := H[q0] * |0>",
        stop_after="mqt_lower",
    ).transpile()

    scenario = result.scenario_results[0]
    assert scenario.status == "completed"
    assert any(stage.stage_id == "placement" and stage.status == "skipped_by_policy" for stage in scenario.stage_results)


def test_run43_identity_native_transpile_does_not_create_false_transformation_event():
    result = CQ.pipeline(equation="|psi> := H[q0] * |0>").transpile()

    events = result.scenario_results[0].transformation_graph.events
    assert [event.stage_id for event in events if event.stage_id == "native_transpile"] == []
    assert result.scenario_results[0].transpilation_record["transformations"] == []


def test_run43_measurement_contract_is_tracked_by_stage():
    result = CQ.pipeline(equation="|psi> := H[q0] * |0>").run_engine(shots=8)

    contracts = result.scenario_results[0].artifacts["measurement_contracts_by_stage"]
    assert {"mqt_lower", "emission", "native_transpile", "compilation", "execution", "decoding"}.issubset(contracts)
    assert contracts["execution"].automatic is True


def test_run43_explicit_adapter_descriptor_is_preserved():
    class CustomInput:
        pass

    class Adapter:
        adapter_id = "custom-v2-ish"
        navigation_version = "v2"
        engine_origin = "neutral"
        exactness = "exact"
        limitations = ("test-only",)

        def supports(self, value):
            return isinstance(value, CustomInput)

        def adapt(self, value, context):
            builder = CQ.circuit(1)
            builder.x(0)
            return builder.build()

    result = CQ.pipeline(input=CustomInput(), input_adapter=Adapter()).transpile()
    descriptor = result.scenario_results[0].artifacts["input_adapter"]

    assert descriptor.adapter_id == "custom-v2-ish"
    assert descriptor.navigation_version == "v2"
    assert descriptor.output_format == "ir"


def test_run43_physical_target_without_executor_binding_does_not_fall_back_to_aer():
    target = CQ.manual_target(
        target_id="physical-only",
        qubits=1,
        operations=[{"name": "h", "arity": 1}, {"name": "measure", "arity": 1}],
        target_type="physical",
    )
    circuit = CQ.circuit(1)
    circuit.h(0)

    with pytest.raises(Exception, match="target fisico|target apenas analisado|executor-target"):
        CQ.run_engine(circuit.build(), target=target, shots=4)

