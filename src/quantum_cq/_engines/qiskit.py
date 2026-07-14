"""Qiskit engine adapter."""

from __future__ import annotations

from typing import Any

from quantum_cq._circuits.adapters import export_to_qiskit
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError, ResultDecodingError
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class QiskitEngineAdapter:
    engine_id = "qiskit"

    def is_installed(self) -> bool:
        try:
            import qiskit  # noqa: F401
        except ImportError:
            return False
        return True

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            engine=self.engine_id,
            installed=self.is_installed(),
            default=True,
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
                "mcx": "supported",
                "ccx": "supported",
                "observables": "supported",
                "gradients": "not_tested",
                "local_execution": "supported",
                "remote_execution": "supported",
                "async_jobs": "supported",
            },
        )

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        _ = options
        return export_to_qiskit(circuit_like)

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        emitted = self.emit(circuit_like)
        backend = options.get("backend")
        pass_manager = options.get("pass_manager")
        optimization_level = options.get("optimization_level")
        native_compiled = emitted

        if pass_manager is not None:
            native_compiled = pass_manager.run(emitted)
        elif backend is not None and optimization_level is not None:
            try:
                from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
            except ImportError as exc:
                raise EngineNotInstalledError("Qiskit transpiler is not available") from exc

            native_compiled = generate_preset_pass_manager(
                backend=backend,
                optimization_level=optimization_level,
            ).run(emitted)

        return CompiledArtifact(
            engine=self.engine_id,
            emitted_circuit=emitted,
            native_compiled=native_compiled,
            backend=backend,
            options=dict(options),
            metadata={"compiled": native_compiled is not emitted},
        )

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        artifact = (
            circuit_like
            if isinstance(circuit_like, CompiledArtifact)
            else self.compile(circuit_like, **options)
        )
        circuit = artifact.native_compiled.copy()
        if circuit.num_clbits == 0 or circuit.count_ops().get("measure", 0) == 0:
            circuit.measure_all()

        try:
            from qiskit_aer import AerSimulator
        except ImportError as exc:
            raise EngineNotInstalledError(
                "Qiskit local execution requires qiskit-aer; install quantum-cq[aer]."
            ) from exc

        try:
            simulator = options.get("simulator") or AerSimulator()
            job = simulator.run(circuit, shots=shots)
            raw = job.result()
            counts = raw.get_counts()
        except Exception as exc:
            raise ExecutionError("Qiskit execution failed") from exc

        if not isinstance(counts, dict):
            raise ResultDecodingError("Qiskit result did not provide counts")

        return EngineResult(
            engine=self.engine_id,
            counts={str(key): int(value) for key, value in counts.items()},
            metadata={
                "shots": shots,
                "backend": getattr(simulator, "name", None),
                "bit_order": "qiskit_counts_order",
            },
            raw=raw,
        )
