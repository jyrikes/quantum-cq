"""SDK-free custom unitary values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import log2
from types import MappingProxyType
from typing import Any

import numpy as np


class UnitaryValidationError(ValueError):
    """Raised when a user supplied matrix is not a valid unitary."""


@dataclass(frozen=True)
class CustomUnitary:
    matrix: tuple[tuple[complex, ...], ...]
    name: str = "unitary"
    num_qubits: int = 0
    atol: float = 1e-8
    metadata: Mapping[str, Any] = field(default_factory=dict)
    qubit_order: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        matrix = tuple(tuple(complex(value) for value in row) for row in self.matrix)
        object.__setattr__(self, "matrix", matrix)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "qubit_order", tuple(self.qubit_order or range(self.num_qubits)))

    def as_array(self) -> np.ndarray:
        return np.array(self.matrix, dtype=complex, copy=True)

    def __array__(self, dtype: Any = None) -> np.ndarray:
        return np.array(self.matrix, dtype=dtype or complex, copy=True)


def create_unitary(
    matrix: Any,
    *,
    name: str | None = None,
    validate: bool = True,
    atol: float | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CustomUnitary:
    tolerance = 1e-8 if atol is None else float(atol)
    copied = np.array(matrix, dtype=complex, copy=True)
    if copied.ndim != 2:
        raise UnitaryValidationError("Unitary matrix must be two-dimensional")
    rows, cols = copied.shape
    if rows != cols:
        raise UnitaryValidationError("Unitary matrix must be square")
    if rows == 0 or rows & (rows - 1):
        raise UnitaryValidationError("Unitary matrix dimension must be a power of two")
    num_qubits = int(log2(rows))
    if validate:
        identity = np.eye(rows, dtype=complex)
        if not np.allclose(copied.conj().T @ copied, identity, atol=tolerance):
            raise UnitaryValidationError("Matrix is not unitary within the requested tolerance")
    immutable = tuple(tuple(complex(value) for value in row) for row in copied.tolist())
    return CustomUnitary(
        matrix=immutable,
        name=name or "unitary",
        num_qubits=num_qubits,
        atol=tolerance,
        metadata=metadata or {},
        qubit_order=tuple(range(num_qubits)),
    )


def unitary_payload(
    unitary: CustomUnitary | Sequence[Sequence[complex]],
    qubits: Sequence[int],
    *,
    name: str | None = None,
) -> dict[str, Any]:
    qubits_tuple = tuple(qubits)
    value = unitary if isinstance(unitary, CustomUnitary) else create_unitary(unitary, name=name)
    if len(qubits_tuple) != value.num_qubits:
        raise UnitaryValidationError(
            f"Unitary '{value.name}' requires {value.num_qubits} qubits, got {len(qubits_tuple)}"
        )
    return {
        "matrix": value.matrix,
        "name": value.name,
        "num_qubits": value.num_qubits,
        "atol": value.atol,
        "target_order": qubits_tuple,
        "metadata": value.metadata,
    }
