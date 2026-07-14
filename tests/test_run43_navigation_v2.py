import numpy as np
import pytest

from quantum_cq import (
    CQ,
    StructuralField,
    StructuralHeap,
    StructuralNode,
    StructuralSelector,
    StructuralType,
)
from quantum_cq._navigation.structural import StructuralNavigationError
from quantum_cq.navigation import structural_heap_to_graph_data, structural_heap_to_walk_topology


def _list_heap(ids=("a", "b"), values=(1, 2)):
    node_type = StructuralType(
        "Node",
        (
            StructuralField("payload", "uint", bit_width=2, semantic_role="value"),
            StructuralField("link", "reference", nullable=True, semantic_role="next"),
        ),
    )
    first, second = ids
    return StructuralHeap(
        (node_type,),
        (
            StructuralNode(second, "Node", {"payload": values[1], "link": None}),
            StructuralNode(first, "Node", {"payload": values[0], "link": second}),
        ),
        roots=(first,),
    )


def _tree_heap():
    node_type = StructuralType(
        "Tree",
        (
            StructuralField("value", "uint", bit_width=2, semantic_role="value"),
            StructuralField("kids", "reference_list", nullable=True, semantic_role="child", ordered=True),
            StructuralField("up", "reference", nullable=True, semantic_role="parent"),
        ),
        strict_tree=True,
        allow_sharing=False,
    )
    return StructuralHeap(
        (node_type,),
        (
            StructuralNode("root", "Tree", {"value": 1, "kids": ("left", "right"), "up": None}),
            StructuralNode("right", "Tree", {"value": 3, "kids": (), "up": "root"}),
            StructuralNode("left", "Tree", {"value": 2, "kids": (), "up": "root"}),
        ),
        roots=("root",),
        allow_sharing=False,
    )


def _graph_heap():
    node_type = StructuralType(
        "Vertex",
        (
            StructuralField("value", "uint", bit_width=2, semantic_role="value"),
            StructuralField("adj", "reference_list", nullable=True, semantic_role="neighbor", ordered=True),
        ),
    )
    return StructuralHeap(
        (node_type,),
        (
            StructuralNode("v0", "Vertex", {"value": 0, "adj": ("v1", "v2")}),
            StructuralNode("v1", "Vertex", {"value": 1, "adj": ("v0",)}),
            StructuralNode("v2", "Vertex", {"value": 2, "adj": ("v0",)}),
        ),
        roots=("v0",),
    )


def _assert_xor_table(result):
    from qiskit.quantum_info import Operator

    matrix = Operator(CQ.to_qiskit(result.circuit)).data
    width = result.plan.pointer_width
    out_width = result.plan.output_width
    for address, value in enumerate(result.plan.memory_values):
        for output in range(2**out_width):
            source = address + (output << width)
            target = address + ((output ^ value) << width)
            assert np.isclose(matrix[target, source], 1.0)
    assert np.allclose(matrix.conj().T @ matrix, np.eye(matrix.shape[0]))
    assert np.allclose(matrix @ matrix, np.eye(matrix.shape[0]))


def test_navigation_v2_read_builds_exact_v1_lowered_ir_and_operator():
    result = CQ.navigation_v2(_list_heap(), operation="read", selector=StructuralSelector.value("payload"))

    assert result.navigation_version == "v2"
    assert result.circuit_format == "ir"
    assert result.plan.lowering_strategy == "explicit_exact"
    assert result.metadata["lowering_backend"] == "navigation_v1"
    assert result.plan.memory_values[:3] == (1, 2, 0)
    assert result.verification.finite_domain_semantic_verification is True
    _assert_xor_table(result)


def test_navigation_v2_canonicalization_is_independent_of_local_ids_and_insertion_order():
    left = CQ.navigation_v2(_list_heap(("a", "b")), operation="read", selector="payload")
    right = CQ.navigation_v2(_list_heap(("x", "y")), operation="read", selector="payload")
    different = CQ.navigation_v2(_list_heap(("x", "y"), values=(1, 3)), operation="read", selector="payload")

    assert left.plan.equivalence_class.equivalence_fingerprint == right.plan.equivalence_class.equivalence_fingerprint
    assert left.plan.equivalence_class.equivalence_fingerprint != different.plan.equivalence_class.equivalence_fingerprint
    assert left.plan.equivalence_class.local_to_canonical == {"a": "n0", "b": "n1"}


def test_navigation_v2_selector_uses_semantic_role_not_field_name():
    node_type = StructuralType(
        "Node",
        (
            StructuralField("next", "reference", nullable=True, semantic_role="reference"),
            StructuralField("actual_link", "reference", nullable=True, semantic_role="next"),
            StructuralField("value", "uint", bit_width=1, semantic_role="value"),
        ),
    )
    heap = StructuralHeap(
        (node_type,),
        (
            StructuralNode("a", "Node", {"next": None, "actual_link": "b", "value": 0}),
            StructuralNode("b", "Node", {"next": None, "actual_link": None, "value": 1}),
        ),
        roots=("a",),
    )

    role_based = CQ.navigation_v2(heap, operation="next")
    wrong_name = CQ.navigation_v2(heap, operation="next", selector="next")

    assert role_based.plan.memory_values[0] == 1
    assert wrong_name.plan.memory_values[0] == wrong_name.plan.null_encoding


def test_navigation_v2_parent_child_neighbor_and_null_are_explicit():
    child = CQ.navigation_v2(_tree_heap(), operation="child", selector=StructuralSelector.role("child", index=1))
    parent = CQ.navigation_v2(_tree_heap(), operation="parent")
    neighbor = CQ.navigation_v2(_graph_heap(), operation="neighbor", selector=StructuralSelector.role("neighbor", index=1))

    assert child.plan.memory_values[0] in {1, 2}
    assert parent.plan.memory_values[parent.plan.null_encoding] == parent.plan.null_encoding
    assert neighbor.plan.memory_values[0] in {1, 2}

    no_parent_type = StructuralType(
        "Node",
        (StructuralField("child", "reference", nullable=True, semantic_role="child"),),
    )
    no_parent = StructuralHeap(
        (no_parent_type,),
        (StructuralNode("a", "Node", {"child": None}),),
        roots=("a",),
    )
    result = CQ.navigation_v2(no_parent, operation="parent")
    assert result.plan.memory_values[0] == result.plan.null_encoding


def test_navigation_v2_compare_pointer_is_null_is_reversible():
    result = CQ.navigation_v2(_list_heap(), operation="compare", predicate="pointer_is_null")

    assert result.plan.output_width == 1
    assert result.plan.memory_values[result.plan.null_encoding] == 1
    assert result.plan.memory_values[0] == 0
    _assert_xor_table(result)


def test_navigation_v2_validation_rejects_invalid_structures_and_ambiguous_options():
    broken = StructuralHeap(
        (StructuralType("Node", (StructuralField("ref", "reference", semantic_role="next"),)),),
        (StructuralNode("a", "Node", {"ref": "missing"}),),
        roots=("a",),
    )
    with pytest.raises(StructuralNavigationError, match="referencia invalida"):
        CQ.navigation_v2(broken, operation="next")

    with pytest.raises(StructuralNavigationError, match="predicate"):
        CQ.navigation_v2(_list_heap(), operation="read", selector="payload", predicate="pointer_is_null")

    with pytest.raises(StructuralNavigationError, match="exactness"):
        CQ.navigation_v2(_list_heap(), operation="read", selector="payload", exactness="approximate")


def test_navigation_v2_pipeline_requires_explicit_structural_adapter():
    result = CQ.navigation_v2(_list_heap(), operation="read", selector="payload")

    pipeline_result = CQ.pipeline(structural_navigation=result).transpile()
    scenario = pipeline_result.scenario_results[0]
    stages = [stage.stage_id for stage in scenario.stage_results]

    assert scenario.status == "completed"
    assert stages[:5] == [
        "navigation_v2_validate",
        "navigation_v2_canonicalize",
        "navigation_v2_plan",
        "navigation_v2_lower",
        "navigation_v2_verify",
    ]
    assert scenario.artifacts["input_adapter"].navigation_version == "v2"
    assert scenario.artifacts["navigation_plan"].navigation_version == "v2"

    with pytest.raises(TypeError, match="StructuralNavigationResult"):
        CQ.pipeline(circuit=result).transpile()


def test_navigation_v2_compile_and_run_use_pipeline_adapter():
    pytest.importorskip("qiskit_aer")
    result = CQ.navigation_v2(_list_heap(), operation="read", selector="payload")

    compiled = CQ.compile(result)
    executed = CQ.run_engine(result, shots=8)
    pipeline_compiled = CQ.pipeline(structural_navigation=result).compile(engine="qiskit")

    assert compiled.engine == "qiskit"
    assert pipeline_compiled.scenario_results[0].artifacts["input_adapter"].adapter_id == "navigation_v2_structural_result"
    assert pipeline_compiled.scenario_results[0].compiled_artifact.engine == "qiskit"
    assert executed.counts


def test_navigation_v1_defaults_remain_available_and_do_not_trigger_v2_stages():
    nav = CQ.nav([1, 2])
    graph_nav = CQ.graph_nav(CQ.graph([(0, 1)], vertices=2))
    walk = CQ.walk(CQ.graph([(0, 1)], vertices=2), steps=1, format="ir")

    assert nav.metadata["navigation_name"] == "addressed_memory"
    assert graph_nav.metadata["navigation_name"] == "graph_navigation"
    assert walk.metadata["navigation_source"] == "graph_navigation"
    assert CQ.available_navigation_encodings() == ["addressed_memory", "graph_navigation"]

    result = CQ.pipeline(circuit=nav).transpile()
    assert not any(stage.stage_id.startswith("navigation_v2_") for stage in result.scenario_results[0].stage_results)


def test_navigation_v2_graph_and_walk_conversions_are_explicit():
    heap = _graph_heap()

    graph = structural_heap_to_graph_data(heap, relation_role="neighbor", directed=True)
    topology = structural_heap_to_walk_topology(heap, relation_role="neighbor")

    assert graph.num_vertices == 3
    assert graph.directed is True
    assert graph.metadata["navigation_version_source"] == "v2"
    assert graph.metadata["conversion"] == "structural_heap_to_graph_data"
    assert topology.vertices == (0, 1, 2)
    assert topology.provenance["conversion"] == "structural_heap_to_walk_topology"

    with pytest.raises(TypeError, match="GraphData"):
        CQ.walk(heap)


def test_navigation_v2_renyi_and_spectral_metrics_are_informational():
    plain = CQ.navigation_v2(
        _graph_heap(),
        operation="neighbor",
        selector=StructuralSelector.role("neighbor", index=0),
    )
    analyzed = CQ.navigation_v2(
        _graph_heap(),
        operation="neighbor",
        selector=StructuralSelector.role("neighbor", index=0),
        access_distribution={"v0": 0.5, "v1": 0.25, "v2": 0.25},
        spectral_limit=4,
    )

    renyi = analyzed.plan.resource_estimates["renyi_h2"]
    spectral = analyzed.plan.resource_estimates["spectral"]

    assert analyzed.plan.memory_values == plain.plan.memory_values
    assert analyzed.plan.equivalence_class.equivalence_fingerprint == plain.plan.equivalence_class.equivalence_fingerprint
    assert renyi["status"] == "computed"
    assert renyi["unit"] == "bits"
    assert spectral["status"] == "computed"
    assert len(spectral["spectrum"]) == 3
