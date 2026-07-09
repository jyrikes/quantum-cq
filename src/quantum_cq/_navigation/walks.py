"""Quantum walk discreto sobre estruturas navegaveis pequenas."""

from __future__ import annotations

from typing import Any

import numpy as np

from quantum_cq._core.interfaces import CircuitBuilderProtocol, CircuitFactoryProtocol
from quantum_cq._navigation.memory import GraphData
from quantum_cq._core.results import OperatorCircuit


def _factory_or_default(circuit_factory: CircuitFactoryProtocol | None) -> CircuitFactoryProtocol:
    if circuit_factory is not None:
        return circuit_factory

    from quantum_cq._circuits.adapters import QiskitCircuitFactory

    return QiskitCircuitFactory()


class CoinedQuantumWalkPrimitive:
    name = "coined_quantum_walk"
    family = "operator"

    def __init__(self, circuit_factory: CircuitFactoryProtocol | None = None) -> None:
        self.circuit_factory = circuit_factory

    def build(self, graph: GraphData, *, steps: int = 1, format: str = "qiskit") -> OperatorCircuit:
        if format != "qiskit":
            raise NotImplementedError(f"CoinedQuantumWalkPrimitive ainda nao implementa build(format='{format}')")
        if not isinstance(graph, GraphData):
            raise TypeError("CoinedQuantumWalkPrimitive espera GraphData")
        if steps <= 0:
            raise ValueError("steps deve ser positivo")

        total_qubits = graph.degree_qubits + graph.vertex_qubits
        builder = _factory_or_default(self.circuit_factory).create(total_qubits)
        self.apply(builder, graph, steps=steps)
        return OperatorCircuit(
            circuit=builder.build(),
            operator_name="coined_quantum_walk_step",
            circuit_format="qiskit",
            metadata=self._metadata(graph, steps=steps),
        )

    def apply(self, builder: CircuitBuilderProtocol, graph: GraphData, *, steps: int = 1) -> None:
        if steps <= 0:
            raise ValueError("steps deve ser positivo")

        total_qubits = graph.degree_qubits + graph.vertex_qubits
        coin_qubits = list(range(graph.degree_qubits))
        all_qubits = list(range(total_qubits))
        shift_matrix = self._shift_matrix(graph)

        for _ in range(steps):
            for qubit in coin_qubits:
                builder.h(qubit)
            builder.unitary(shift_matrix, all_qubits, label="walk_shift")

    def _shift_mapping(self, graph: GraphData) -> dict[int, int]:
        dimension = 2 ** (graph.degree_qubits + graph.vertex_qubits)
        mapping: dict[int, int] = {}

        for input_index in range(dimension):
            coin = input_index & (graph.degree_space - 1)
            vertex = input_index >> graph.degree_qubits

            if vertex >= graph.num_vertices or coin >= len(graph.neighbors(vertex)):
                output_index = input_index
            else:
                target_vertex = graph.neighbor(vertex, coin)
                reverse_coin = graph.reverse_index(vertex, coin)
                output_index = (target_vertex << graph.degree_qubits) + reverse_coin

            mapping[input_index] = output_index

        if len(set(mapping.values())) != dimension:
            raise ValueError("shift do quantum walk deve ser reversivel")

        return mapping

    def _shift_matrix(self, graph: GraphData) -> np.ndarray:
        mapping = self._shift_mapping(graph)
        dimension = len(mapping)
        matrix = np.zeros((dimension, dimension), dtype=complex)
        for input_index, output_index in mapping.items():
            matrix[output_index, input_index] = 1.0
        return matrix

    def _metadata(self, graph: GraphData, *, steps: int) -> dict[str, Any]:
        return {
            "family": "operator",
            "role": "quantum_walk",
            "unitary_role": "walk_step",
            "operator_name": "coined_quantum_walk_step",
            "graph_vertices": graph.num_vertices,
            "max_degree": graph.max_degree,
            "degree_space": graph.degree_space,
            "vertex_qubits": graph.vertex_qubits,
            "coin_qubits": graph.degree_qubits,
            "steps": steps,
            "coin_model": "hadamard_padded",
            "shift_model": "explicit_permutation",
            "uses_addressed_navigation": True,
            "uses_addressed_navigation_semantics": True,
            "navigation_source": "graph_navigation",
            "status": "implemented_mvp",
        }


__all__ = ["CoinedQuantumWalkPrimitive"]
