"""PennyLane engine adapter."""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np

from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError
from quantum_cq._engines.logical import iter_operations, to_logical_ir
from quantum_cq._engines.lowering import lower_for_capabilities
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class PennyLaneEngineAdapter:
    engine_id = "pennylane"

    def is_installed(self) -> bool:
        return importlib.util.find_spec("pennylane") is not None

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
                "gradients": "not_tested",
                "local_execution": "supported",
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
            },
        )

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        qml = self._require_pennylane()
        ir = lower_for_capabilities(to_logical_ir(circuit_like), self.capabilities())
        operations = [
            self._operation(qml, operation)
            for operation in iter_operations(ir)
            if operation.kind != "measure"
        ]
        measurements = [qml.sample(wires=range(ir.n_qubits))]
        return qml.tape.QuantumScript(operations, measurements, shots=options.get("shots"))

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        qml = self._require_pennylane()
        ir = lower_for_capabilities(to_logical_ir(circuit_like), self.capabilities())
        emitted = self.emit(ir, **options)
        device = options.get("device") or qml.device(
            options.get("device_name", "default.qubit"),
            wires=ir.n_qubits,
            shots=options.get("shots", 1024),
        )

        @qml.qnode(device)
        def executable():
            for operation in iter_operations(ir):
                if operation.kind == "measure":
                    continue
                self._apply(qml, operation)
            return qml.sample(wires=range(ir.n_qubits))

        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted,
            native_compiled=executable,
            device=device,
            options=dict(options),
            metadata={"logical_qubits": ir.n_qubits},
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        options = {**options, "shots": shots}
        artifact = (
            circuit_like
            if isinstance(circuit_like, CompiledArtifact)
            else self.compile(circuit_like, **options)
        )
        try:
            samples = artifact.native_compiled()
        except Exception as exc:
            raise ExecutionError("PennyLane execution failed") from exc

        counts = _samples_to_counts(samples)
        return EngineResult(
            engine=self.engine_id,
            counts=counts,
            samples=samples,
            metadata={"shots": shots, "device": str(artifact.device), "bit_order": "qiskit_counts_order"},
            raw=samples,
        )

    def _require_pennylane(self):
        try:
            import pennylane as qml
        except ImportError as exc:
            raise EngineNotInstalledError(
                "PennyLane is not installed; install quantum-cq[pennylane]."
            ) from exc
        return qml

    def _operation(self, qml, operation):
        with qml.queuing.QueuingManager.stop_recording():
            return self._make_operation(qml, operation)

    def _apply(self, qml, operation) -> None:
        self._make_operation(qml, operation)

    def _make_operation(self, qml, operation):
        kind = operation.kind
        if kind == "x":
            return qml.PauliX(wires=operation.qubits[0])
        if kind == "y":
            return qml.PauliY(wires=operation.qubits[0])
        if kind == "z":
            return qml.PauliZ(wires=operation.qubits[0])
        if kind == "h":
            return qml.Hadamard(wires=operation.qubits[0])
        if kind == "rx":
            return qml.RX(operation.params["theta"], wires=operation.qubits[0])
        if kind == "ry":
            return qml.RY(operation.params["theta"], wires=operation.qubits[0])
        if kind == "rz":
            return qml.RZ(operation.params["theta"], wires=operation.qubits[0])
        if kind == "p":
            return qml.PhaseShift(operation.params["theta"], wires=operation.qubits[0])
        if kind == "cx":
            return qml.CNOT(wires=[operation.params["control"], operation.params["target"]])
        if kind == "cz":
            return qml.CZ(wires=[operation.params["control"], operation.params["target"]])
        if kind == "swap":
            return qml.SWAP(wires=[operation.params["left"], operation.params["right"]])
        if kind == "ccx":
            return qml.Toffoli(wires=list(operation.qubits))
        raise ExecutionError(f"PennyLane adapter does not support operation '{kind}'")


def _samples_to_counts(samples: Any) -> dict[str, int]:
    array = np.asarray(samples)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    counts: dict[str, int] = {}
    for row in array:
        bitstring = "".join(str(int(bit)) for bit in reversed(row.tolist()))
        counts[bitstring] = counts.get(bitstring, 0) + 1
    return counts
