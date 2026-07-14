import numpy as np
import pytest
from qiskit.quantum_info import Operator

from quantum_cq import CQ
from quantum_cq.navigation import GraphData
from quantum_cq.results import OperatorCircuit


def test_coined_quantum_walk_builds_unitary_for_cycle_graph():
    cycle = CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4)
    walk = CQ.primitive("coined_quantum_walk").build(cycle, steps=1)

    assert isinstance(walk, OperatorCircuit)
    assert walk.operator_name == "coined_quantum_walk_step"
    assert walk.metadata["role"] == "quantum_walk"
    assert walk.metadata["uses_addressed_navigation_semantics"] is True
    assert walk.metadata["navigation_source"] == "graph_navigation"
    assert walk.metadata["shift_model"] == "flip_flop"
    assert walk.metadata["evolution_convention"] == "W = S C"
    assert walk.metadata["lowering_strategy"] == "dense_exact"
    assert walk.metadata["status"] == "implemented_exact_dense"

    matrix = np.asarray(Operator(CQ.to_qiskit(walk)).data, dtype=complex)
    identity = np.eye(matrix.shape[0])
    assert matrix.conj().T @ matrix == pytest.approx(identity)


def test_coined_quantum_walk_steps_and_registry_return_fresh_instances():
    cycle = GraphData(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4)
    first = CQ.primitive("coined_quantum_walk")
    second = CQ.primitive("coined_quantum_walk")
    walk = first.build(cycle, steps=2)

    assert first is not second
    assert walk.metadata["steps"] == 2
    assert CQ.to_qiskit(walk).num_qubits == cycle.degree_qubits + cycle.vertex_qubits


def test_coined_quantum_walk_padding_directions_are_identity_in_shift():
    graph = GraphData(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4)
    primitive = CQ.primitive("coined_quantum_walk")
    shift = primitive._shift_mapping(graph)

    padded_input = (0 << graph.degree_qubits) + 1
    assert shift[padded_input] == padded_input


def test_coined_quantum_walk_rejects_non_reversible_shift():
    directed = GraphData(edges=[(0, 1), (1, 2)], num_vertices=3, directed=True)

    with pytest.raises(ValueError, match="reversivel"):
        CQ.primitive("coined_quantum_walk").build(directed, steps=1)
