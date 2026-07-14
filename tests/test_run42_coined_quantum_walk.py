import numpy as np
import pytest
from qiskit.quantum_info import Operator, Statevector

from quantum_cq import CQ
from quantum_cq._navigation.coined import QuantumWalkError, build_quantum_walk_plan


def test_run42_coined_walk_cycle_c4_unitarity_and_powers():
    graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4)
    one = build_quantum_walk_plan(graph, steps=1)
    two = build_quantum_walk_plan(graph, steps=2)

    _assert_unitary(one.coin_matrix)
    _assert_unitary(one.shift_matrix)
    assert one.shift_matrix @ one.shift_matrix == pytest.approx(np.eye(one.topology.dimension))
    _assert_unitary(one.step_matrix)
    assert two.evolution_matrix == pytest.approx(one.step_matrix @ one.step_matrix)
    assert one.step_matrix == pytest.approx(_reference_walk_matrix(graph, steps=1))


def test_run42_coined_walk_irregular_path_preserves_padding_and_norm():
    graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4)
    plan = build_quantum_walk_plan(graph, steps=3)

    assert plan.topology.degree_by_vertex == {0: 1, 1: 2, 2: 2, 3: 1}
    for vertex, coin in plan.topology.padding_states:
        index = _index(plan, vertex, coin)
        basis = np.zeros(plan.topology.dimension, dtype=complex)
        basis[index] = 1.0
        assert plan.coin_matrix @ basis == pytest.approx(basis)
        assert plan.shift_matrix @ basis == pytest.approx(basis)
    state = np.zeros(plan.topology.dimension, dtype=complex)
    state[0] = 1.0
    evolved = plan.evolution_matrix @ state
    assert np.linalg.norm(evolved) == pytest.approx(1.0)


def test_run42_coined_walk_star_has_local_grover_coin_and_leaf_identity():
    graph = CQ.graph(edges=[(0, 1), (0, 2), (0, 3)], num_vertices=4)
    plan = build_quantum_walk_plan(graph, steps=1)
    center_degree = 3
    expected_center = (2.0 / center_degree) * np.ones((center_degree, center_degree)) - np.eye(center_degree)

    center_block = plan.coin_matrix[:4, :4]

    assert center_block[:3, :3] == pytest.approx(expected_center)
    assert center_block[3, 3] == pytest.approx(1.0)
    for leaf in (1, 2, 3):
        base = leaf << plan.topology.coin_qubits
        assert plan.coin_matrix[base, base] == pytest.approx(1.0)
    _assert_unitary(plan.step_matrix)


def test_run42_coined_walk_isolated_vertex_is_identity():
    graph = CQ.graph(edges=[], num_vertices=1)
    plan = build_quantum_walk_plan(graph, steps=4)

    assert plan.topology.isolated_vertices == (0,)
    assert plan.topology.dimension == 1
    assert plan.evolution_matrix == pytest.approx(np.eye(1))


def test_run42_coined_walk_rejects_invalid_graph_and_coins():
    directed = CQ.graph(edges=[(0, 1), (1, 2)], num_vertices=3, directed=True)
    with pytest.raises(QuantumWalkError, match="reversivel"):
        build_quantum_walk_plan(directed)

    cycle = CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4)
    with pytest.raises(QuantumWalkError, match="dimensao"):
        build_quantum_walk_plan(cycle, coin=np.eye(4))

    path = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4)
    with pytest.raises(QuantumWalkError, match="padding"):
        build_quantum_walk_plan(path, coin=CQ.unitary([[0, 1], [1, 0]], name="custom_coin"))

    with pytest.raises(ValueError, match="not unitary|unitaria|unitary"):
        build_quantum_walk_plan(cycle, coin=[[1, 1], [0, 1]])


def test_run42_coined_walk_lowers_to_pipeline_and_qiskit_statevector_matches_reference():
    for graph in (
        CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], num_vertices=4),
        CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4),
        CQ.graph(edges=[(0, 1), (0, 2), (0, 3)], num_vertices=4),
    ):
        walk = CQ.walk(graph, steps=2, format="ir")
        compiled = CQ.pipeline(circuit=walk, engine="qiskit").compile()
        qiskit_circuit = CQ.to_qiskit(walk)
        reference = _reference_walk_matrix(graph, steps=2)
        state = Statevector.from_instruction(qiskit_circuit).data

        assert compiled.compiled_artifact.engine == "qiskit"
        assert Operator(qiskit_circuit).data == pytest.approx(reference)
        assert state == pytest.approx(reference[:, 0])


def _assert_unitary(matrix):
    assert matrix.conj().T @ matrix == pytest.approx(np.eye(matrix.shape[0]))


def _reference_walk_matrix(graph, *, steps):
    neighbors = {vertex: tuple(graph.neighbors(vertex)) for vertex in range(graph.num_vertices)}
    max_degree = max((len(values) for values in neighbors.values()), default=0)
    position_qubits = _ceil_log2(max(1, graph.num_vertices))
    coin_qubits = _ceil_log2(max(1, max_degree))
    coin_space = 2**coin_qubits
    dimension = 2 ** (position_qubits + coin_qubits)
    coin = np.eye(dimension, dtype=complex)
    shift = np.eye(dimension, dtype=complex)
    for vertex, local in neighbors.items():
        degree = len(local)
        if degree:
            grover = (2.0 / degree) * np.ones((degree, degree), dtype=complex) - np.eye(degree)
            for row in range(degree):
                for col in range(degree):
                    coin[_raw_index(vertex, row, coin_qubits), _raw_index(vertex, col, coin_qubits)] = grover[row, col]
        for port, target in enumerate(local):
            reverse = neighbors[target].index(vertex)
            shift[_raw_index(target, reverse, coin_qubits), _raw_index(vertex, port, coin_qubits)] = 1.0
            if _raw_index(target, reverse, coin_qubits) != _raw_index(vertex, port, coin_qubits):
                shift[_raw_index(vertex, port, coin_qubits), _raw_index(vertex, port, coin_qubits)] = 0.0
    return np.linalg.matrix_power(shift @ coin, steps)


def _index(plan, vertex, coin):
    return (vertex << plan.topology.coin_qubits) + coin


def _raw_index(vertex, coin, coin_qubits):
    return (vertex << coin_qubits) + coin


def _ceil_log2(value):
    if int(value) <= 1:
        return 0
    return int(np.ceil(np.log2(int(value))))
