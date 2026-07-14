"""Exact finite discrete-time coined quantum walk semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import ceil, log2, sqrt
from types import MappingProxyType
from typing import Any

import numpy as np

from quantum_cq._circuits.compact import CircuitIR, LogicalCircuitBuilder
from quantum_cq._circuits.unitary import CustomUnitary, create_unitary
from quantum_cq._navigation.memory import GraphData


class QuantumWalkError(ValueError):
    pass


class QuantumWalkCapacityError(QuantumWalkError):
    pass


@dataclass(frozen=True)
class WalkArc:
    source: int
    port: int
    target: int
    reverse_port: int


@dataclass(frozen=True)
class WalkTopology:
    vertices: tuple[int, ...]
    neighbors: dict[int, tuple[int, ...]]
    arcs: tuple[WalkArc, ...]
    edges: tuple[tuple[int, int], ...]
    max_degree: int
    position_qubits: int
    coin_qubits: int
    coin_space: int
    valid_states: tuple[tuple[int, int], ...]
    padding_states: tuple[tuple[int, int], ...]
    isolated_vertices: tuple[int, ...]
    fingerprint: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "vertices", tuple(self.vertices))
        object.__setattr__(
            self,
            "neighbors",
            MappingProxyType({int(key): tuple(values) for key, values in self.neighbors.items()}),
        )
        object.__setattr__(self, "arcs", tuple(self.arcs))
        object.__setattr__(self, "edges", tuple(tuple(edge) for edge in self.edges))
        object.__setattr__(self, "valid_states", tuple(tuple(item) for item in self.valid_states))
        object.__setattr__(self, "padding_states", tuple(tuple(item) for item in self.padding_states))
        object.__setattr__(self, "isolated_vertices", tuple(self.isolated_vertices))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def dimension(self) -> int:
        return 2 ** (self.position_qubits + self.coin_qubits)

    @property
    def degree_by_vertex(self) -> dict[int, int]:
        return {vertex: len(self.neighbors[vertex]) for vertex in self.vertices}


@dataclass(frozen=True)
class QuantumWalkPlan:
    topology: WalkTopology
    coin_model: str
    shift_model: str
    steps: int
    register_layout: dict[str, Any]
    exactness: str
    lowering_strategy: str
    coin_matrix: np.ndarray
    shift_matrix: np.ndarray
    step_matrix: np.ndarray
    evolution_matrix: np.ndarray
    metrics: dict[str, Any] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("coin_matrix", "shift_matrix", "step_matrix", "evolution_matrix"):
            matrix = np.array(getattr(self, field_name), dtype=complex, copy=True)
            matrix.setflags(write=False)
            object.__setattr__(self, field_name, matrix)
        object.__setattr__(self, "register_layout", MappingProxyType(dict(self.register_layout)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


def build_walk_topology(graph: GraphData) -> WalkTopology:
    if not isinstance(graph, GraphData):
        raise TypeError("coined quantum walk espera GraphData")
    _reject_duplicate_edges(graph)
    vertices = tuple(range(graph.num_vertices))
    neighbors = {vertex: tuple(graph.neighbors(vertex)) for vertex in vertices}
    if graph.directed:
        _validate_directed_reverses(neighbors)
    edges = tuple(sorted({tuple(sorted((left, right))) for left, right in graph.edges}))
    max_degree = max((len(values) for values in neighbors.values()), default=0)
    position_qubits = _ceil_log2(max(1, graph.num_vertices))
    coin_qubits = _ceil_log2(max(1, max_degree))
    coin_space = 2**coin_qubits
    arcs: list[WalkArc] = []
    valid_states: list[tuple[int, int]] = []
    padding_states: list[tuple[int, int]] = []
    isolated: list[int] = []
    for vertex in vertices:
        local_neighbors = neighbors[vertex]
        if not local_neighbors:
            isolated.append(vertex)
        for port in range(coin_space):
            if port < len(local_neighbors):
                target = local_neighbors[port]
                reverse_neighbors = neighbors[target]
                if vertex not in reverse_neighbors:
                    raise QuantumWalkError("grafo direcionado sem porta reversa comprovada; shift nao e reversivel")
                reverse = reverse_neighbors.index(vertex)
                arcs.append(WalkArc(vertex, port, target, reverse))
                valid_states.append((vertex, port))
            else:
                padding_states.append((vertex, port))
    vertex_space = 2**position_qubits
    for vertex in range(graph.num_vertices, vertex_space):
        for port in range(coin_space):
            padding_states.append((vertex, port))
    payload = {
        "vertices": vertices,
        "neighbors": {str(key): values for key, values in neighbors.items()},
        "position_qubits": position_qubits,
        "coin_qubits": coin_qubits,
        "padding_policy": graph.padding_policy,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return WalkTopology(
        vertices=vertices,
        neighbors=neighbors,
        arcs=tuple(arcs),
        edges=edges,
        max_degree=max_degree,
        position_qubits=position_qubits,
        coin_qubits=coin_qubits,
        coin_space=coin_space,
        valid_states=tuple(valid_states),
        padding_states=tuple(padding_states),
        isolated_vertices=tuple(isolated),
        fingerprint=fingerprint,
        provenance={"source": "GraphData", "directed": graph.directed},
    )


def build_quantum_walk_plan(
    graph: GraphData,
    *,
    steps: int = 1,
    coin: str | CustomUnitary | Any = "grover",
    shift: str = "flip_flop",
    max_dimension: int = 64,
    atol: float = 1e-8,
) -> QuantumWalkPlan:
    if int(steps) <= 0:
        raise QuantumWalkError("steps deve ser positivo")
    if shift != "flip_flop":
        raise QuantumWalkError(f"shift nao suportado: {shift}")
    topology = build_walk_topology(graph)
    if topology.dimension > int(max_dimension):
        raise QuantumWalkCapacityError(
            f"dense_exact requer dimensao <= {max_dimension}; recebido {topology.dimension}"
        )
    coin_model = coin if isinstance(coin, str) else getattr(coin, "name", "custom")
    coin_matrix = _coin_matrix(topology, coin=coin, atol=atol)
    shift_matrix = _shift_matrix(topology)
    step_matrix = shift_matrix @ coin_matrix
    evolution = np.linalg.matrix_power(step_matrix, int(steps))
    _assert_unitary(coin_matrix, atol=atol, label="coin")
    _assert_unitary(shift_matrix, atol=atol, label="shift")
    _assert_unitary(step_matrix, atol=atol, label="walk step")
    _assert_unitary(evolution, atol=atol, label="walk evolution")
    metrics = {
        "vertices": len(topology.vertices),
        "edges": len(topology.edges),
        "arcs": len(topology.arcs),
        "degree_by_vertex": topology.degree_by_vertex,
        "max_degree": topology.max_degree,
        "position_qubits": topology.position_qubits,
        "coin_qubits": topology.coin_qubits,
        "physical_dimension": topology.dimension,
        "valid_states": len(topology.valid_states),
        "padding_states": len(topology.padding_states),
        "steps": int(steps),
        "matrix_dimension": topology.dimension,
    }
    return QuantumWalkPlan(
        topology=topology,
        coin_model=str(coin_model),
        shift_model=shift,
        steps=int(steps),
        register_layout={
            "flat_index": "(vertex << coin_qubits) + coin",
            "coin_qubits": tuple(range(topology.coin_qubits)),
            "position_qubits": tuple(range(topology.coin_qubits, topology.coin_qubits + topology.position_qubits)),
        },
        exactness="finite_exact",
        lowering_strategy="dense_exact",
        coin_matrix=coin_matrix,
        shift_matrix=shift_matrix,
        step_matrix=step_matrix,
        evolution_matrix=evolution,
        metrics=metrics,
        provenance={"convention": "W = S C", "applies": "coin then shift"},
    )


def lower_walk_plan_to_ir(plan: QuantumWalkPlan) -> CircuitIR:
    total_qubits = plan.topology.position_qubits + plan.topology.coin_qubits
    builder = LogicalCircuitBuilder(
        total_qubits,
        name="coined_quantum_walk",
        metadata={
            "role": "quantum_walk",
            "walk_topology_fingerprint": plan.topology.fingerprint,
            "coin_model": plan.coin_model,
            "shift_model": plan.shift_model,
            "steps": plan.steps,
            "lowering_strategy": plan.lowering_strategy,
            "evolution_convention": "W = S C",
            "walk_metrics": dict(plan.metrics),
        },
    )
    if total_qubits:
        builder.unitary(plan.evolution_matrix, tuple(range(total_qubits)), label="coined_walk_evolution")
    return builder.build()


def _coin_matrix(topology: WalkTopology, *, coin: str | CustomUnitary | Any, atol: float) -> np.ndarray:
    dimension = topology.dimension
    matrix = np.eye(dimension, dtype=complex)
    for vertex in range(2**topology.position_qubits):
        degree = len(topology.neighbors.get(vertex, ()))
        local = _local_coin(topology, degree, coin=coin, atol=atol)
        for row in range(topology.coin_space):
            for col in range(topology.coin_space):
                matrix[_index(topology, vertex, row), _index(topology, vertex, col)] = local[row, col]
    return matrix


def _local_coin(topology: WalkTopology, degree: int, *, coin: str | CustomUnitary | Any, atol: float) -> np.ndarray:
    coin_space = topology.coin_space
    if degree <= 0:
        return np.eye(coin_space, dtype=complex)
    if isinstance(coin, str):
        normalized = coin.lower()
        if normalized == "identity":
            return np.eye(coin_space, dtype=complex)
        if normalized == "grover":
            valid = (2.0 / degree) * np.ones((degree, degree), dtype=complex) - np.eye(degree, dtype=complex)
            return _embed_valid_coin(valid, coin_space, degree)
        if normalized == "hadamard":
            if degree != coin_space or coin_space not in {1, 2}:
                raise QuantumWalkError("coin Hadamard requer dimensao valida sem padding")
            if coin_space == 1:
                return np.eye(1, dtype=complex)
            return np.array([[1, 1], [1, -1]], dtype=complex) / sqrt(2)
        raise QuantumWalkError(f"coin nao suportada: {coin}")
    custom = coin if isinstance(coin, CustomUnitary) else create_unitary(coin, name="custom_coin")
    custom_matrix = custom.as_array()
    if custom_matrix.shape != (coin_space, coin_space):
        raise QuantumWalkError("coin customizada deve ter dimensao igual ao espaco de coin fisico")
    if degree != coin_space:
        raise QuantumWalkError("coin customizada nesta run requer ausencia de padding local")
    _assert_unitary(custom_matrix, atol=atol, label="custom coin")
    return custom_matrix


def _embed_valid_coin(valid: np.ndarray, coin_space: int, degree: int) -> np.ndarray:
    matrix = np.eye(coin_space, dtype=complex)
    matrix[:degree, :degree] = valid
    return matrix


def _shift_matrix(topology: WalkTopology) -> np.ndarray:
    mapping = _shift_mapping(topology)
    matrix = np.zeros((topology.dimension, topology.dimension), dtype=complex)
    for source, target in mapping.items():
        matrix[target, source] = 1.0
    return matrix


def _shift_mapping(topology: WalkTopology) -> dict[int, int]:
    mapping = {index: index for index in range(topology.dimension)}
    for arc in topology.arcs:
        mapping[_index(topology, arc.source, arc.port)] = _index(topology, arc.target, arc.reverse_port)
    if len(set(mapping.values())) != topology.dimension:
        raise QuantumWalkError("flip-flop shift deve ser uma permutacao bijetiva")
    return mapping


def _index(topology: WalkTopology, vertex: int, coin: int) -> int:
    return (int(vertex) << topology.coin_qubits) + int(coin)


def _ceil_log2(value: int) -> int:
    if int(value) <= 1:
        return 0
    return int(ceil(log2(int(value))))


def _assert_unitary(matrix: np.ndarray, *, atol: float, label: str) -> None:
    identity = np.eye(matrix.shape[0], dtype=complex)
    if not np.allclose(matrix.conj().T @ matrix, identity, atol=atol):
        raise QuantumWalkError(f"{label} nao e unitario dentro da tolerancia")


def _reject_duplicate_edges(graph: GraphData) -> None:
    seen: set[tuple[int, int]] = set()
    for left, right in graph.edges:
        edge = (int(left), int(right)) if graph.directed else tuple(sorted((int(left), int(right))))
        if edge in seen:
            raise QuantumWalkError("multigrafos nao sao suportados nesta run")
        seen.add(edge)


def _validate_directed_reverses(neighbors: dict[int, tuple[int, ...]]) -> None:
    for source, values in neighbors.items():
        for target in values:
            if source not in neighbors.get(target, ()):
                raise QuantumWalkError("grafo direcionado sem arco reverso explicito; shift nao e reversivel")


__all__ = [
    "QuantumWalkCapacityError",
    "QuantumWalkError",
    "QuantumWalkPlan",
    "WalkArc",
    "WalkTopology",
    "build_quantum_walk_plan",
    "build_walk_topology",
    "lower_walk_plan_to_ir",
]
