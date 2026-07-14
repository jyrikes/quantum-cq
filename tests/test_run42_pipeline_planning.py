import pytest

from quantum_cq import CQ, NativeInstruction, TopologyEdge
from quantum_cq.experiment import PipelineResult
from quantum_cq._planning import PlanningError, place, route, schedule


def test_run42_scenarios_use_independent_effective_configuration():
    result = CQ.pipeline(
        equation="|psi> := RY(theta)[q0] * |0>",
        scenarios=[
            {"scenario_id": "left", "parameters": {"theta": 0.125}, "shots": 8},
            {"scenario_id": "right", "parameters": {"theta": 0.5}, "shots": 16},
        ],
    ).transpile()

    left, right = result.scenario_results

    assert left.logical_circuit.layers[0].operations[0].params["theta"] == 0.125
    assert right.logical_circuit.layers[0].operations[0].params["theta"] == 0.5
    assert left.scenario_id == "left"
    assert right.scenario_id == "right"
    assert left is not right


def test_run42_stages_and_stop_after_control_execution():
    result = CQ.pipeline(
        equation="|psi> := H[q0] * |0>",
        placement="identity",
        stages=("mqt_lower", "placement"),
        stop_after="placement",
    ).transpile()

    stages = [(stage.stage_id, stage.status) for stage in result.scenario_results[0].stage_results]

    assert ("mqt_lower", "completed") in stages
    assert ("placement", "completed") in stages
    assert ("routing", "skipped_by_policy") in stages
    assert ("scheduling", "skipped_by_policy") in stages
    assert ("native_transpile", "skipped_by_policy") in stages
    assert "compiled_artifact" not in result.scenario_results[0].artifacts


def test_run42_routing_materializes_swaps_and_schedule_consumes_routed_circuit():
    circuit = _long_range_cx()
    target = _line_target(include_swap=True, include_durations=True)

    placement = place(circuit, target=target, strategy="identity")
    routing = route(circuit, target=target, placement=placement, strategy="shortest_path")
    routed_ops = [op.kind for layer in routing.routed_circuit.layers for op in layer.operations]
    scheduled = schedule(routing.routed_circuit, target=target, strategy="asap")

    assert routing.swaps == (("p0", "p1"),)
    assert routing.routed_circuit is not circuit
    assert routed_ops[:2] == ["swap", "cx"]
    assert dict(routing.initial_mapping) == {0: "p0", 1: "p1", 2: "p2"}
    assert dict(routing.final_mapping) == {0: "p1", 1: "p0", 2: "p2"}
    assert scheduled.status == "completed"
    assert [item.operation_kind for item in scheduled.items][:2] == ["swap", "cx"]


def test_run42_pipeline_records_routed_snapshot_and_schedule():
    result = CQ.pipeline(
        circuit=_long_range_cx(),
        target=_line_target(include_swap=True, include_durations=True),
        placement="identity",
        routing="shortest_path",
        scheduling="asap",
        stages=("input_adapt", "placement", "routing", "scheduling"),
        stop_after="scheduling",
    ).transpile()
    scenario = result.scenario_results[0]

    assert scenario.artifacts["routing_plan"].swaps == (("p0", "p1"),)
    assert scenario.artifacts["schedule"].status == "completed"
    assert any(snapshot.stage_id == "routed" for snapshot in scenario.snapshots)
    assert any(event.stage_id == "routing" for event in scenario.transformation_graph.events)


def test_run42_routing_rejects_missing_swap_support_and_bad_direction():
    circuit = _long_range_cx()
    placement = place(circuit, target=_line_target(include_swap=False), strategy="identity")

    with pytest.raises(PlanningError, match="SWAP"):
        route(circuit, target=_line_target(include_swap=False), placement=placement, strategy="shortest_path")

    reverse = CQ.circuit(2)
    reverse.cx(1, 0)
    target = CQ.manual_target(
        target_id="directed",
        qubits=("p0", "p1"),
        operations=(NativeInstruction("cx", arity=2),),
        topology=(TopologyEdge("p0", "p1", directed=True, operations=("cx",)),),
        target_type="simulator_ideal",
    )
    with pytest.raises(PlanningError, match="incompatible"):
        route(reverse.build(), target=target, strategy="shortest_path")


def test_run42_fingerprint_is_sensitive_to_params_and_unitary_matrix():
    theta_a = CQ.pipeline(equation="|psi> := RY(theta)[q0] * |0>", parameters={"theta": 0.1}).transpile()
    theta_b = CQ.pipeline(equation="|psi> := RY(theta)[q0] * |0>", parameters={"theta": 0.2}).transpile()

    assert theta_a.before_transpile.snapshot_id != theta_b.before_transpile.snapshot_id

    first = CQ.circuit(1)
    first.unitary(CQ.unitary([[0, 1], [1, 0]], name="U"), [0])
    second = CQ.circuit(1)
    second.unitary(CQ.unitary([[1, 0], [0, -1]], name="U"), [0])

    first_result = CQ.pipeline(circuit=first.build()).transpile()
    second_result = CQ.pipeline(circuit=second.build()).transpile()

    assert first_result.before_transpile.snapshot_id != second_result.before_transpile.snapshot_id


def test_run42_run_engine_executes_the_compiled_artifact_in_result():
    pytest.importorskip("qiskit_aer")

    result = CQ.pipeline(equation="|psi> := H[q0] * |0>").run_engine(engine="qiskit", shots=8)

    assert isinstance(result, PipelineResult)
    assert result.compiled_artifact is not None
    assert result.engine_result is not None
    assert result.engine_result.metadata["compiled_artifact_identity"] == id(result.compiled_artifact)


def _long_range_cx():
    circuit = CQ.circuit(3, 3)
    circuit.cx(0, 2)
    circuit.measure(0, 0)
    circuit.measure(2, 2)
    return circuit.build()


def _line_target(*, include_swap: bool, include_durations: bool = False):
    restrictions = {"duration": 1} if include_durations else {}
    operations = [
        NativeInstruction("cx", arity=2, restrictions=restrictions),
        NativeInstruction("measure", arity=1, restrictions=restrictions),
    ]
    edge_ops = ["cx"]
    if include_swap:
        operations.append(NativeInstruction("swap", arity=2, restrictions=restrictions))
        edge_ops.append("swap")
    return CQ.manual_target(
        target_id=f"line-swap-{include_swap}",
        qubits=("p0", "p1", "p2"),
        operations=tuple(operations),
        topology=(
            TopologyEdge("p0", "p1", directed=False, operations=tuple(edge_ops)),
            TopologyEdge("p1", "p2", directed=False, operations=tuple(edge_ops)),
        ),
        target_type="simulator_ideal",
    )
