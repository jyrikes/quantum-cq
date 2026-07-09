"""Coleta simples de metricas de circuitos."""

from __future__ import annotations

from typing import Any

from quantum_cq._core.results import AlgorithmCircuit, EncodedCircuit, NavigationCircuit, OperatorCircuit, OracleCircuit


_METADATA_KEYS = {
    "algorithm_name",
    "encoding_name",
    "operator_name",
    "oracle_name",
    "navigation_name",
    "oracle_calls",
    "operator_calls",
    "primitive_calls",
    "family",
    "role",
    "natural_encoding",
    "supported_encodings",
    "unitary_role",
    "oracle_type",
    "iterations",
    "marked_state",
    "estimated_phase",
    "expected_output",
    "expected_phase",
    "cost_model",
    "status",
    "bit_order",
    "model",
    "engine",
    "delegated_engine",
    "physical_qram",
    "simulates_qram_semantics",
    "simulates_physical_qram",
    "access_semantics",
    "reversible",
    "address_bit_order",
    "data_bit_order",
    "address_qubits",
    "data_qubits",
    "memory_size",
    "address_space_size",
    "default_value",
    "nonzero_entries",
    "skipped_zero_entries",
    "num_vertices",
    "graph_vertices",
    "max_degree",
    "degree_space",
    "vertex_qubits",
    "degree_qubits",
    "neighbor_qubits",
    "construction_cost",
    "coin_qubits",
    "steps",
    "coin_model",
    "shift_model",
    "uses_addressed_navigation",
    "uses_addressed_navigation_semantics",
    "navigation_source",
}


class MetricsCollector:
    def collect(self, circuit, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        from quantum_cq._circuits.adapters import circuit_format_of, export_to_qiskit

        metadata = self._metadata(circuit)
        circuit_format = circuit_format_of(circuit)
        qiskit_circuit = export_to_qiskit(circuit)
        count_ops = dict(qiskit_circuit.count_ops())
        metrics = {
            "num_qubits": qiskit_circuit.num_qubits,
            "num_clbits": qiskit_circuit.num_clbits,
            "depth": qiskit_circuit.depth(),
            "size": qiskit_circuit.size(),
            "count_ops": count_ops,
            "num_cx": count_ops.get("cx", 0),
            "num_mcx": count_ops.get("mcx", 0),
            "num_swap": count_ops.get("swap", 0),
            "num_cp": count_ops.get("cp", 0),
            "num_2q_gates": self._count_two_qubit_ops(count_ops),
            "num_measurements": count_ops.get("measure", 0),
            "circuit_format": circuit_format,
        }

        for key in _METADATA_KEYS:
            if key in metadata:
                metrics[key] = metadata[key]

        if extra:
            metrics.update(extra)

        return metrics

    def _metadata(self, value: Any) -> dict[str, Any]:
        if isinstance(value, EncodedCircuit):
            metadata = dict(value.metadata)
            metadata.setdefault("encoding_name", value.encoding_name)
            return metadata

        if isinstance(value, AlgorithmCircuit):
            metadata = dict(value.metadata)
            metadata.setdefault("algorithm_name", value.algorithm_name)
            metadata.setdefault("circuit_format", value.circuit_format)
            return metadata

        if isinstance(value, OperatorCircuit):
            metadata = dict(value.metadata)
            metadata.setdefault("operator_name", value.operator_name)
            metadata.setdefault("circuit_format", value.circuit_format)
            return metadata

        if isinstance(value, OracleCircuit):
            metadata = dict(value.metadata)
            metadata.setdefault("oracle_name", value.oracle_name)
            metadata.setdefault("circuit_format", value.circuit_format)
            return metadata

        if isinstance(value, NavigationCircuit):
            metadata = dict(value.metadata)
            metadata.setdefault("navigation_name", value.navigation_name)
            metadata.setdefault("circuit_format", value.circuit_format)
            return metadata

        return {}

    def _count_two_qubit_ops(self, count_ops: dict[str, int]) -> int:
        two_qubit_names = {"cx", "cz", "cp", "swap"}
        return sum(count_ops.get(name, 0) for name in two_qubit_names)
