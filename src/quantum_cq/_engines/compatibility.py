"""Engine compatibility reexports.

The compatibility contracts are SDK-free core DTOs. This module preserves the
RUN 2 import path for engine code and public tests.
"""

from quantum_cq._core.compatibility import (
    CompatibilityEvaluator,
    CompatibilityReport,
    CompatibilityStatus,
    ComponentRequirement,
    normalize_requirement,
)

__all__ = [
    "CompatibilityEvaluator",
    "CompatibilityReport",
    "CompatibilityStatus",
    "ComponentRequirement",
    "normalize_requirement",
]
