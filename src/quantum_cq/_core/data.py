"""Estruturas de dados para entrada clássica."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuantumData:
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
