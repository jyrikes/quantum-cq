"""CUDA-Q availability adapter."""

from __future__ import annotations

import importlib.util
import platform
from typing import Any

from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import EngineNotInstalledError, ExecutionError
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class CudaQEngineAdapter:
    engine_id = "cudaq"

    def is_installed(self) -> bool:
        return importlib.util.find_spec("cudaq") is not None

    def capabilities(self) -> EngineCapabilities:
        system = platform.system().lower()
        installed = self.is_installed()
        if system == "windows":
            status = "unsupported"
            reason = "CUDA-Q is not supported on native Windows; use WSL or a supported Linux/macOS environment."
        elif installed:
            status = "experimental"
            reason = "CUDA-Q package detected, but this run does not claim functional coverage without engine tests."
        else:
            status = "not_tested"
            reason = "CUDA-Q package is not installed in this environment."

        return EngineCapabilities(
            engine=self.engine_id,
            installed=installed,
            statuses={
                "x": status,
                "y": status,
                "z": status,
                "h": status,
                "rx": status,
                "ry": status,
                "rz": status,
                "cx": status,
                "cz": status,
                "swap": status,
                "measure": status,
                "parameterized": status,
                "mcx": "unsupported",
                "ccx": status,
                "observables": "not_tested",
                "gradients": "not_tested",
                "local_execution": status,
                "remote_execution": "unsupported",
                "async_jobs": "unsupported",
            },
            metadata={
                "system": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "reason": reason,
            },
        )

    def emit(self, circuit_like: Any, **options: Any) -> Any:
        _ = circuit_like, options
        raise EngineNotInstalledError(self.capabilities().metadata["reason"])

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact:
        _ = circuit_like, options
        raise EngineNotInstalledError(self.capabilities().metadata["reason"])

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult:
        _ = circuit_like, shots, options
        raise ExecutionError(self.capabilities().metadata["reason"])
