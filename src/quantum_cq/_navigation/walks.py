"""Quantum walk discreto sobre estruturas navegaveis pequenas."""

from __future__ import annotations

from typing import Any

from quantum_cq._core.interfaces import CircuitBuilderProtocol, CircuitFactoryProtocol
from quantum_cq._navigation.memory import GraphData
from quantum_cq._core.results import OperatorCircuit
from quantum_cq._navigation.coined import build_quantum_walk_plan, lower_walk_plan_to_ir


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

    def build(
        self,
        graph: GraphData,
        *,
        steps: int = 1,
        coin: Any = "grover",
        shift: str = "flip_flop",
        format: str = "qiskit",
        max_dimension: int = 64,
        atol: float = 1e-8,
    ) -> OperatorCircuit:
        if format not in {"qiskit", "ir"}:
            raise NotImplementedError(f"CoinedQuantumWalkPrimitive ainda nao implementa build(format='{format}')")
        if not isinstance(graph, GraphData):
            raise TypeError("CoinedQuantumWalkPrimitive espera GraphData")
        plan = build_quantum_walk_plan(
            graph,
            steps=steps,
            coin=coin,
            shift=shift,
            max_dimension=max_dimension,
            atol=atol,
        )
        ir = lower_walk_plan_to_ir(plan)
        if format == "ir":
            circuit = ir
            circuit_format = "ir"
        else:
            from quantum_cq._circuits.adapters import export_to_qiskit

            circuit = export_to_qiskit(ir)
            circuit_format = "qiskit"
        return OperatorCircuit(
            circuit=circuit,
            operator_name="coined_quantum_walk_step",
            circuit_format=circuit_format,
            metadata=self._metadata(plan),
        )

    def plan(self, graph: GraphData, **options: Any):
        return build_quantum_walk_plan(graph, **options)

    def apply(self, builder: CircuitBuilderProtocol, graph: GraphData, *, steps: int = 1) -> None:
        plan = build_quantum_walk_plan(graph, steps=steps)
        total_qubits = plan.topology.position_qubits + plan.topology.coin_qubits
        if total_qubits:
            builder.unitary(plan.evolution_matrix, list(range(total_qubits)), label="coined_walk_evolution")

    def _shift_mapping(self, graph: GraphData) -> dict[int, int]:
        plan = build_quantum_walk_plan(graph, steps=1, coin="identity")
        matrix = plan.shift_matrix
        mapping: dict[int, int] = {}
        for source in range(matrix.shape[1]):
            column = matrix[:, source]
            target = int(max(range(len(column)), key=lambda index: abs(column[index])))
            mapping[source] = target
        return mapping

    def _metadata(self, plan) -> dict[str, Any]:
        graph_metrics = dict(plan.metrics)
        return {
            "family": "operator",
            "role": "quantum_walk",
            "unitary_role": "walk_evolution",
            "operator_name": "coined_quantum_walk",
            "graph_vertices": graph_metrics["vertices"],
            "graph_edges": graph_metrics["edges"],
            "graph_arcs": graph_metrics["arcs"],
            "degree_by_vertex": graph_metrics["degree_by_vertex"],
            "max_degree": graph_metrics["max_degree"],
            "physical_dimension": graph_metrics["physical_dimension"],
            "valid_states": graph_metrics["valid_states"],
            "padding_states": graph_metrics["padding_states"],
            "vertex_qubits": graph_metrics["position_qubits"],
            "position_qubits": graph_metrics["position_qubits"],
            "coin_qubits": graph_metrics["coin_qubits"],
            "steps": plan.steps,
            "coin_model": plan.coin_model,
            "shift_model": plan.shift_model,
            "evolution_convention": "W = S C",
            "lowering_strategy": plan.lowering_strategy,
            "walk_topology_fingerprint": plan.topology.fingerprint,
            "uses_addressed_navigation": True,
            "uses_addressed_navigation_semantics": True,
            "navigation_source": "graph_navigation",
            "status": "implemented_exact_dense",
        }


__all__ = ["CoinedQuantumWalkPrimitive"]
