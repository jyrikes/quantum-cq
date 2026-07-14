"""Common engine artifacts and result wrappers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CompiledArtifact:
    engine: str
    emitted_circuit: Any
    native_compiled: Any
    backend: Any = None
    device: Any = None
    options: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineResult:
    engine: str
    counts: Mapping[str, int] | None = None
    probabilities: Mapping[str, float] | None = None
    samples: Any = None
    expectation_values: tuple[float, ...] | None = None
    statevector: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Any = None
