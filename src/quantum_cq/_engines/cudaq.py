"""CUDA-Q availability ports."""

from __future__ import annotations

import importlib.util
import platform
from importlib import metadata
from typing import Any

from quantum_cq._engines.availability import EngineAvailability
from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError, ResultDecodingError
from quantum_cq._engines.results import CompiledArtifact, EngineResult, NativeExecutionResult


ENGINE_ID = "cudaq"


class CudaQAvailabilityPort:
    engine_id = ENGINE_ID

    def availability(self) -> EngineAvailability:
        system = platform.system()
        machine = platform.machine()
        installed = importlib.util.find_spec("cudaq") is not None
        version = None
        if installed:
            try:
                version = metadata.version("cudaq")
            except metadata.PackageNotFoundError:
                version = None

        if system.lower() == "windows":
            return EngineAvailability(
                engine=self.engine_id,
                installed=installed,
                compatible=False,
                version=version,
                reason="CUDA-Q is not supported on native Windows; use WSL or a supported Linux/macOS environment.",
                metadata={"system": system, "machine": machine, "python": platform.python_version()},
            )
        if installed:
            return EngineAvailability(
                engine=self.engine_id,
                installed=True,
                compatible=True,
                version=version,
                reason="CUDA-Q package detected, but this run does not claim functional coverage without engine tests.",
                metadata={"system": system, "machine": machine, "python": platform.python_version()},
            )
        return EngineAvailability(
            engine=self.engine_id,
            installed=False,
            compatible=False,
            reason="CUDA-Q package is not installed in this environment.",
            metadata={"system": system, "machine": machine, "python": platform.python_version()},
        )

    def is_installed(self) -> bool:
        return self.availability().installed


class CudaQCapabilitiesPort:
    engine_id = ENGINE_ID

    def __init__(self, availability: CudaQAvailabilityPort | None = None) -> None:
        self._availability = availability or CudaQAvailabilityPort()

    def capabilities(self) -> EngineCapabilities:
        availability = self._availability.availability()
        if availability.compatible and availability.installed:
            status = "experimental"
        elif platform.system().lower() == "windows":
            status = "unsupported"
        else:
            status = "not_tested"
        return EngineCapabilities(
            engine=self.engine_id,
            installed=availability.installed,
            statuses={
                "x": status,
                "y": status,
                "z": status,
                "h": status,
                "p": status,
                "rx": status,
                "ry": status,
                "rz": status,
                "cx": status,
                "cz": status,
                "cp": "not_tested",
                "swap": status,
                "measure": status,
                "partial_measurement": "not_tested",
                "mapped_measurement": "not_tested",
                "auto_measure_all": "not_tested",
                "intermediate_measurement": "not_tested",
                "parameterized": status,
                "mcx": "unsupported",
                "ccx": status,
                "unitary": "not_tested",
                "observables": "not_tested",
                "gradients": "not_tested",
                "statevector": "not_tested",
                "noise": "not_tested",
                "local_execution": status,
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
            },
            metadata={**availability.metadata, "reason": availability.reason},
        )


class CudaQUnavailablePort:
    engine_id = ENGINE_ID

    def __init__(self, availability: CudaQAvailabilityPort | None = None) -> None:
        self._availability = availability or CudaQAvailabilityPort()

    def emit(self, circuit_ir: Any, **options: Any) -> Any:
        _ = circuit_ir, options
        raise EngineNotInstalledError(self._availability.availability().reason)

    def compile(self, emitted_circuit: Any, **options: Any) -> CompiledArtifact:
        _ = emitted_circuit, options
        raise EngineNotInstalledError(self._availability.availability().reason)

    def execute(self, artifact: CompiledArtifact, *, shots: int = 1024, **options: Any) -> NativeExecutionResult:
        _ = artifact, shots, options
        raise ExecutionError(self._availability.availability().reason)

    def decode(
        self,
        execution: NativeExecutionResult,
        artifact: CompiledArtifact,
        *,
        shots: int = 1024,
        **options: Any,
    ) -> EngineResult:
        _ = execution, artifact, shots, options
        raise ResultDecodingError(self._availability.availability().reason)


class CudaQEngineAdapter:
    engine_id = ENGINE_ID

    def __init__(self) -> None:
        self._bundle = create_bundle()

    def is_installed(self) -> bool:
        return self._bundle.availability.is_installed()

    def capabilities(self) -> EngineCapabilities:
        return self._bundle.capabilities.capabilities()

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        return self._bundle.emitter.emit(circuit_like, **options)

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        return self._bundle.compiler.compile(circuit_like, **options)

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        execution = self._bundle.executor.execute(circuit_like, shots=shots, **options)
        return self._bundle.decoder.decode(execution, circuit_like, shots=shots, **options)


def create_bundle() -> EngineBundle:
    availability = CudaQAvailabilityPort()
    unavailable = CudaQUnavailablePort(availability)
    return EngineBundle(
        engine_id=ENGINE_ID,
        availability=availability,
        capabilities=CudaQCapabilitiesPort(availability),
        emitter=unavailable,
        compiler=unavailable,
        executor=unavailable,
        decoder=unavailable,
    )
