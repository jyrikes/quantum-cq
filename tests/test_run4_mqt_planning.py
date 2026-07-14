from datetime import datetime, timezone

import pytest

from quantum_cq import CQ
from quantum_cq._circuits.compact import CircuitIR, Layer, Operation
from quantum_cq._hardware.models import NativeInstruction, TargetArchitecture, TopologyEdge
from quantum_cq._mqt import MQTParseError, MQTSemanticError, lower_to_circuit, parse_equation, semantic_program
from quantum_cq._planning import PlanningError, place, route, schedule
from quantum_cq._runtime.unified import PipelineScenario, PipelineState, StageResult


def test_mqt_unicode_and_ascii_forms_lower_to_same_circuit():
    unicode = """
    |ψ⟩ := CX[q0,q1] · (H[q0] ⊗ I[q1]) · |00⟩
    measure Z[q0,q1] -> c[0,1]
    """
    ascii_equiv = """
    |psi> := CX[q0,q1] * (H[q0] tensor I[q1]) * |00>
    measure Z[q0,q1] -> c[0,1]
    """

    left = lower_to_circuit(semantic_program(parse_equation(unicode)))
    right = lower_to_circuit(semantic_program(parse_equation(ascii_equiv)))

    assert [op.kind for layer in left.layers for op in layer.operations] == ["h", "cx"]
    assert [op.kind for layer in right.layers for op in layer.operations] == ["h", "cx"]
    assert left.outputs == right.outputs


def test_mqt_rejects_multiple_assignments_and_python_like_input():
    with pytest.raises(MQTParseError, match="exatamente uma"):
        parse_equation("|a> := |0>\n|b> := |1>")

    with pytest.raises(MQTParseError, match="insegura"):
        parse_equation("|psi> := __import__[q0] * |0>")


def test_mqt_rejects_reserved_symbol_override_and_unknown_symbol():
    unitary = CQ.unitary([[0, 1], [1, 0]], name="U")

    with pytest.raises(MQTSemanticError, match="reservado"):
        semantic_program(parse_equation("|psi> := H[q0] * |0>"), symbols={"H": unitary})

    with pytest.raises(MQTSemanticError, match="desconhecido"):
        semantic_program(parse_equation("|psi> := A[q0] * |0>"))


def test_mqt_external_unitary_and_partial_measurement():
    unitary = CQ.unitary([[0, 1], [1, 0]], name="U")
    semantic = semantic_program(
        parse_equation("|psi> := U[q0] * |0>\nmeasure Z[q0] -> c[1]"),
        symbols={"U": unitary},
    )

    circuit = lower_to_circuit(semantic)

    assert circuit.n_qubits == 1
    assert circuit.n_clbits == 2
    assert circuit.layers[0].operations[0].kind == "unitary"
    assert circuit.outputs == [Operation("measure", qubits=(0,), clbits=(1,))]


def test_stage_completed_must_produce_declared_features():
    scenario = PipelineScenario("s", "circuit", primary_input=object())
    state = PipelineState(scenario=scenario)
    now = datetime.now(timezone.utc)
    stage = StageResult(
        stage_id="demo",
        status="completed",
        started_at=now,
        finished_at=now,
        provides=("missing_feature",),
    )

    with pytest.raises(ValueError, match="completed sem produzir"):
        state.with_stage(stage)


def test_planning_identity_placement_is_bijective():
    circuit = _cx_ir(0, 1)
    target = _target(topology=(TopologyEdge("p0", "p1", directed=False, operations=("cx",)),))

    plan = place(circuit, target=target, strategy="identity")

    assert plan.logical_to_physical == {0: "p0", 1: "p1"}
    assert plan.physical_to_logical == {"p0": 0, "p1": 1}


def test_routing_respects_direction_and_swap_capability():
    circuit = _cx_ir(1, 0)
    target = _target(topology=(TopologyEdge("p0", "p1", directed=True, operations=("cx",)),))

    with pytest.raises(PlanningError, match="incompatible"):
        route(circuit, target=target, strategy="shortest_path")

    longer = _target(
        qubits=("p0", "p1", "p2"),
        topology=(
            TopologyEdge("p0", "p1", directed=False, operations=("cx",)),
            TopologyEdge("p1", "p2", directed=False, operations=("cx",)),
        ),
    )
    long_circuit = CircuitIR(
        name="long",
        n_qubits=3,
        n_clbits=0,
        inputs=[],
        layers=[Layer([Operation("cx", qubits=(0, 2), params={"control": 0, "target": 2})])],
        outputs=[],
    )
    with pytest.raises(PlanningError, match="SWAP"):
        route(long_circuit, target=longer, strategy="shortest_path")


def test_scheduling_asap_reports_partial_when_duration_missing():
    circuit = _cx_ir(0, 1)
    target = _target(
        topology=(TopologyEdge("p0", "p1", directed=False, operations=("cx",)),),
        instructions=(NativeInstruction("h", arity=1, restrictions={"duration": 1}),),
    )

    plan = schedule(circuit, target=target, strategy="asap")

    assert plan.complete is False
    assert plan.status == "insufficient_information"
    assert "duracao desconhecida" in plan.diagnostics[0]


def _cx_ir(control, target):
    return CircuitIR(
        name="cx",
        n_qubits=2,
        n_clbits=0,
        inputs=[],
        layers=[Layer([Operation("cx", qubits=(control, target), params={"control": control, "target": target})])],
        outputs=[],
    )


def _target(
    *,
    qubits=("p0", "p1"),
    topology=(),
    instructions=(NativeInstruction("cx", arity=2),),
):
    return CQ.manual_target(
        target_id="manual",
        qubits=qubits,
        operations=instructions,
        topology=topology,
        target_type="simulator_ideal",
    )
