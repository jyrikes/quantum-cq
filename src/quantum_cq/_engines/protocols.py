"""Internal multi-engine protocols."""

from __future__ import annotations

from typing import Any, Protocol

from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.results import CompiledArtifact, EngineResult


class EngineAdapterProtocol(Protocol):
    engine_id: str

    def is_installed(self) -> bool: ...

    def capabilities(self) -> EngineCapabilities: ...

    def emit(self, circuit_like: Any, **options: Any) -> Any: ...

    def compile(self, circuit_like: Any, **options: Any) -> CompiledArtifact: ...

    def run(self, circuit_like: Any, *, shots: int = 1024, **options: Any) -> EngineResult: ...
