"""Cirq engine adapter."""

from __future__ import annotations

import importlib.util
from typing import Any

from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError
from quantum_cq._engines.logical import iter_operations, to_logical_ir
from quantum_cq._engines.lowering import lower_for_capabilities
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class CirqEngineAdapter:
    engine_id = "cirq"

    def is_installed(self) -> bool:
        return importlib.util.find_spec("cirq") is not None

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            engine=self.engine_id,
            installed=self.is_installed(),
            statuses={
                "x": "supported",
                "y": "supported",
                "z": "supported",
                "h": "supported",
                "rx": "supported",
                "ry": "supported",
                "rz": "supported",
                "cx": "supported",
                "cz": "supported",
                "swap": "supported",
                "measure": "supported",
                "parameterized": "supported",
                "mcx": "lowered",
                "ccx": "supported",
                "observables": "not_tested",
                "gradients": "unsupported",
                "local_execution": "supported",
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
            },
        )

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        cirq = self._require_cirq()
        ir = lower_for_capabilities(to_logical_ir(circuit_like), self.capabilities())
        qubits = [cirq.LineQubit(index) for index in range(ir.n_qubits)]
        circuit = cirq.Circuit()
        for operation in iter_operations(ir):
            self._append(cirq, circuit, qubits, operation)
        return circuit

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        emitted = self.emit(circuit_like, **options)
        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted,
            native_compiled=emitted,
            device=options.get("device"),
            options=dict(options),
            metadata={"compiled": False},
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        cirq = self._require_cirq()
        artifact = (
            circuit_like
            if isinstance(circuit_like, CompiledArtifact)
            else self.compile(circuit_like, **options)
        )
        circuit = artifact.native_compiled
        if not _has_measurements(circuit):
            qubits = sorted(circuit.all_qubits())
            circuit = circuit + cirq.Circuit(cirq.measure(*qubits, key="m"))

        try:
            simulator = options.get("simulator") or cirq.Simulator()
            raw = simulator.run(circuit, repetitions=shots)
        except Exception as exc:
            raise ExecutionError("Cirq execution failed") from exc

        counts = _cirq_counts(raw)
        return EngineResult(
            engine=self.engine_id,
            counts=counts,
            metadata={"shots": shots, "bit_order": "qiskit_counts_order"},
            raw=raw,
        )

    def _require_cirq(self):
        try:
            import cirq
        except ImportError as exc:
            raise EngineNotInstalledError("Cirq is not installed; install quantum-cq[cirq].") from exc
        return cirq

    def _append(self, cirq, circuit, qubits, operation) -> None:
        kind = operation.kind
        if kind == "x":
            circuit.append(cirq.X(qubits[operation.qubits[0]]))
        elif kind == "y":
            circuit.append(cirq.Y(qubits[operation.qubits[0]]))
        elif kind == "z":
            circuit.append(cirq.Z(qubits[operation.qubits[0]]))
        elif kind == "h":
            circuit.append(cirq.H(qubits[operation.qubits[0]]))
        elif kind == "rx":
            circuit.append(cirq.rx(operation.params["theta"])(qubits[operation.qubits[0]]))
        elif kind == "ry":
            circuit.append(cirq.ry(operation.params["theta"])(qubits[operation.qubits[0]]))
        elif kind == "rz":
            circuit.append(cirq.rz(operation.params["theta"])(qubits[operation.qubits[0]]))
        elif kind == "cx":
            circuit.append(cirq.CNOT(qubits[operation.params["control"]], qubits[operation.params["target"]]))
        elif kind == "cz":
            circuit.append(cirq.CZ(qubits[operation.params["control"]], qubits[operation.params["target"]]))
        elif kind == "swap":
            circuit.append(cirq.SWAP(qubits[operation.params["left"]], qubits[operation.params["right"]]))
        elif kind == "ccx":
            circuit.append(cirq.CCX(*(qubits[index] for index in operation.qubits)))
        elif kind == "measure":
            circuit.append(cirq.measure(qubits[operation.qubits[0]], key=f"c{operation.clbits[0]}"))
        else:
            raise ExecutionError(f"Cirq adapter does not support operation '{kind}'")


def _has_measurements(circuit) -> bool:
    return any(
        op.gate is not None and op.gate.__class__.__name__ == "MeasurementGate"
        for moment in circuit
        for op in moment
    )


def _cirq_counts(result) -> dict[str, int]:
    if "m" in result.measurements:
        rows = result.measurements["m"]
    else:
        keys = sorted(result.measurements, key=lambda key: int(key[1:]) if key.startswith("c") else key)
        rows = []
        for shot in range(len(next(iter(result.measurements.values())))):
            rows.append([int(result.measurements[key][shot][0]) for key in keys])

    counts: dict[str, int] = {}
    for row in rows:
        bitstring = "".join(str(int(bit)) for bit in reversed(list(row)))
        counts[bitstring] = counts.get(bitstring, 0) + 1
    return counts
