import pytest
from qiskit.quantum_info import Operator

from quantum_cq import CQ
from quantum_cq.navigation import GraphData, GraphNavigationEncoding
from quantum_cq.results import NavigationCircuit


def _basis_output(matrix, input_index):
    column = matrix[:, input_index]
    output_index = max(range(len(column)), key=lambda index: abs(column[index]))
    assert abs(column[output_index]) == pytest.approx(1.0)
    return output_index


def _graph_index(graph, vertex, coin, data_value):
    address = (vertex << graph.degree_qubits) + coin
    address_qubits = graph.vertex_qubits + graph.degree_qubits
    return address + (data_value << address_qubits)


def test_graph_data_uses_deterministic_self_loop_padding_and_flat_memory():
    graph = GraphData(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4, directed=False)

    assert graph.neighbors(0) == [1]
    assert graph.neighbors(1) == [0, 2]
    assert graph.max_degree == 2
    assert graph.degree_space == 2
    assert graph.degree_qubits == 1
    assert graph.vertex_qubits == 2
    assert graph.neighbor(0, 0) == 1
    assert graph.neighbor(0, 1) == 0
    assert graph.reverse_index(0, 1) == 1

    flat = graph.to_flat_memory()
    assert flat.values == [1, 0, 0, 2, 1, 3, 2, 3]
    assert graph.to_metadata()["padding_policy"] == "self_loop"


def test_graph_data_directed_and_invalid_edges():
    directed = GraphData(edges=[(0, 1)], num_vertices=2, directed=True)

    assert directed.neighbors(0) == [1]
    assert directed.neighbors(1) == []
    assert directed.neighbor(1, 0) == 1

    with pytest.raises(ValueError, match="num_vertices"):
        GraphData(edges=[], num_vertices=0)
    with pytest.raises(ValueError, match="vertices"):
        GraphData(edges=[(0, 2)], num_vertices=2)


def test_graph_navigation_encoding_uses_addressed_memory_flattening():
    graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], num_vertices=4)

    nav = CQ.encode(graph, role="navigation")

    assert isinstance(graph, GraphData)
    assert isinstance(nav, NavigationCircuit)
    assert nav.navigation_name == "graph_navigation"
    assert nav.metadata["uses_addressed_memory"] is True
    assert nav.metadata["flat_addressing"] == "v * degree_space + k"
    assert nav.metadata["address_layout"] == "[k bits primeiro] + [v bits depois]"
    assert CQ.metrics(nav)["navigation_name"] == "graph_navigation"
    assert "graph_navigation" in CQ.available_navigation_encodings()

    matrix = Operator(CQ.to_qiskit(nav)).data
    cases = [(0, 0, 0), (0, 1, 0), (1, 1, 2), (2, 0, 1)]
    for vertex, coin, data_value in cases:
        expected_neighbor = graph.neighbor(vertex, coin)
        input_index = _graph_index(graph, vertex, coin, data_value)
        expected = _graph_index(graph, vertex, coin, data_value ^ expected_neighbor)
        assert _basis_output(matrix, input_index) == expected


def test_graph_navigation_manual_encoding_and_qram_like_engine():
    graph = GraphData(edges=[(0, 1), (1, 2)], num_vertices=3)

    manual = CQ.encode(graph, role="navigation", encoding="graph_navigation", engine="qram_like")
    direct = GraphNavigationEncoding(engine="explicit_circuit").build_neighbor_oracle(graph)

    assert manual.metadata["model"] == "qram_like"
    assert manual.metadata["physical_qram"] is False
    assert direct.metadata["model"] == "explicit_circuit"
