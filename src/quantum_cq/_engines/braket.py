"""Amazon Braket engine adapter."""

from __future__ import annotations

import importlib.util
from typing import Any

from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError
from quantum_cq._engines.logical import iter_operations, to_logical_ir
from quantum_cq._engines.lowering import lower_for_capabilities
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class BraketEngineAdapter:
    engine_id = "braket"

    def is_installed(self) -> bool:
        return importlib.util.find_spec("braket") is not None

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
        _ = options
        Circuit = self._require_circuit()
        ir = lower_for_capabilities(to_logical_ir(circuit_like), self.capabilities())
        circuit = Circuit()
        for operation in iter_operations(ir):
            self._append(circuit, operation)
        return circuit

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        emitted = self.emit(circuit_like, **options)
        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted,
            native_compiled=emitted,
            device=options.get("device", "braket.local.qubit"),
            options=dict(options),
            metadata={"compiled": False},
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        artifact = (
            circuit_like
            if isinstance(circuit_like, CompiledArtifact)
            else self.compile(circuit_like, **options)
        )
        try:
            from braket.devices import LocalSimulator
        except ImportError as exc:
            raise EngineNotInstalledError(
                "Amazon Braket local execution requires amazon-braket-sdk; install quantum-cq[braket]."
            ) from exc

        try:
            device = options.get("device") or LocalSimulator()
            task = device.run(artifact.native_compiled, shots=shots)
            raw = task.result()
            counts = dict(raw.measurement_counts)
        except Exception as exc:
            raise ExecutionError("Amazon Braket local execution failed") from exc

        return EngineResult(
            engine=self.engine_id,
            counts={str(key): int(value) for key, value in counts.items()},
            metadata={"shots": shots, "device": str(artifact.device), "bit_order": "braket_measurement_order"},
            raw=raw,
        )

    def _require_circuit(self):
        try:
            from braket.circuits import Circuit
        except ImportError as exc:
            raise EngineNotInstalledError(
                "Amazon Braket SDK is not installed; install quantum-cq[braket]."
            ) from exc
        return Circuit

    def _append(self, circuit, operation) -> None:
        kind = operation.kind
        if kind == "x":
            circuit.x(operation.qubits[0])
        elif kind == "y":
            circuit.y(operation.qubits[0])
        elif kind == "z":
            circuit.z(operation.qubits[0])
        elif kind == "h":
            circuit.h(operation.qubits[0])
        elif kind == "rx":
            circuit.rx(operation.qubits[0], operation.params["theta"])
        elif kind == "ry":
            circuit.ry(operation.qubits[0], operation.params["theta"])
        elif kind == "rz":
            circuit.rz(operation.qubits[0], operation.params["theta"])
        elif kind == "cx":
            circuit.cnot(operation.params["control"], operation.params["target"])
        elif kind == "cz":
            circuit.cz(operation.params["control"], operation.params["target"])
        elif kind == "swap":
            circuit.swap(operation.params["left"], operation.params["right"])
        elif kind == "ccx":
            circuit.ccnot(*operation.qubits)
        elif kind == "measure":
            # Braket local simulator samples all qubits at run time.
            return
        else:
            raise ExecutionError(f"Amazon Braket adapter does not support operation '{kind}'")
