"""Contratos principais do projeto."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, runtime_checkable


T = TypeVar("T")


@runtime_checkable
class CircuitLikeProtocol(Protocol):
    pass


@runtime_checkable
class CircuitBuilderProtocol(Protocol):
    def x(self, qubit: int) -> None: ...

    def h(self, qubit: int) -> None: ...

    def rx(self, theta: float, qubit: int) -> None: ...

    def ry(self, theta: float, qubit: int) -> None: ...

    def rz(self, theta: float, qubit: int) -> None: ...

    def p(self, theta: float, qubit: int) -> None: ...

    def cx(self, control: int, target: int) -> None: ...

    def cz(self, control: int, target: int) -> None: ...

    def cp(self, theta: float, control: int, target: int) -> None: ...

    def mcx(self, controls: Sequence[int], target: int) -> None: ...

    def swap(self, left: int, right: int) -> None: ...

    def unitary(self, matrix: Any, qubits: Sequence[int], label: str | None = None) -> None: ...

    def measure(self, qubit: int, clbit: int) -> None: ...

    def barrier(self) -> None: ...

    def initialize(self, amplitudes: Sequence[complex], qubits: Sequence[int]) -> None: ...

    def measure_all(self) -> None: ...

    def build(self) -> Any: ...


@runtime_checkable
class CircuitFactoryProtocol(Protocol):
    def create(self, num_qubits: int, num_clbits: int = 0) -> CircuitBuilderProtocol: ...


@runtime_checkable
class EncodingProtocol(Protocol):
    name: str
    family: str
    auto_selectable: bool

    def can_handle(self, data: Any) -> bool: ...

    def encode(self, data: Any) -> Any: ...


@runtime_checkable
class StateEncodingProtocol(EncodingProtocol, Protocol):
    def encode(self, data: Any) -> Any: ...


@runtime_checkable
class OracleEncodingProtocol(EncodingProtocol, Protocol):
    def build_oracle(self, data: Any) -> Any: ...


@runtime_checkable
class OperatorEncodingProtocol(EncodingProtocol, Protocol):
    def build_operator(self, data: Any) -> Any: ...


@runtime_checkable
class NavigationEncodingProtocol(EncodingProtocol, Protocol):
    def build_access_oracle(self, structure: Any) -> Any: ...


@runtime_checkable
class AddressedEncodingProtocol(NavigationEncodingProtocol, Protocol):
    pass


@runtime_checkable
class GraphNavigationProtocol(NavigationEncodingProtocol, Protocol):
    pass


@runtime_checkable
class AlgorithmProtocol(Protocol):
    name: str

    def build(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class AlgorithmBuilderProtocol(Protocol):
    name: str

    def build(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class CircuitExporterProtocol(Protocol):
    name: str
    target_format: str

    def export(self, circuit_like: Any) -> Any: ...


@runtime_checkable
class CompilerAdapterProtocol(Protocol):
    name: str

    def compile(self, circuit_like: Any, **options: Any) -> Any: ...


@runtime_checkable
class OracleProtocol(Protocol):
    name: str

    def build(self, *args: Any, **kwargs: Any) -> Any: ...

    def apply(self, builder: CircuitBuilderProtocol, *args: Any, **kwargs: Any) -> None: ...


@runtime_checkable
class PhaseOracleProtocol(OracleProtocol, Protocol):
    pass


@runtime_checkable
class PredicateOracleProtocol(OracleProtocol, Protocol):
    pass


@runtime_checkable
class DiffuserProtocol(Protocol):
    name: str

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None: ...


@runtime_checkable
class StatePreparationProtocol(Protocol):
    name: str

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None: ...


@runtime_checkable
class PrimitiveProtocol(Protocol):
    name: str

    def build(self, *args: Any, **kwargs: Any) -> Any: ...

    def apply(self, builder: CircuitBuilderProtocol, *args: Any, **kwargs: Any) -> None: ...


@runtime_checkable
class OperatorProtocol(Protocol):
    name: str

    def build(self, *args: Any, **kwargs: Any) -> Any: ...

    def apply(self, builder: CircuitBuilderProtocol, *args: Any, **kwargs: Any) -> None: ...


@runtime_checkable
class UnitaryProtocol(OperatorProtocol, Protocol):
    num_qubits: int

    def build(self, *args: Any, **kwargs: Any) -> Any: ...

    def adjoint(self) -> "UnitaryProtocol": ...


@runtime_checkable
class ControlledUnitaryProtocol(UnitaryProtocol, Protocol):
    def controlled(self, num_controls: int = 1) -> "ControlledUnitaryProtocol": ...


@runtime_checkable
class PowerableUnitaryProtocol(UnitaryProtocol, Protocol):
    def power(self, exponent: int) -> "PowerableUnitaryProtocol": ...


@runtime_checkable
class FourierTransformProtocol(Protocol):
    name: str

    def apply(self, builder: CircuitBuilderProtocol, qubits: Sequence[int]) -> None: ...


@runtime_checkable
class ArithmeticOracleProtocol(OracleProtocol, Protocol):
    pass


@runtime_checkable
class HamiltonianEncodingProtocol(Protocol):
    name: str

    def apply(self, builder: CircuitBuilderProtocol, *args: Any, **kwargs: Any) -> None: ...


@runtime_checkable
class BlockEncodingProtocol(Protocol):
    name: str

    def apply(self, builder: CircuitBuilderProtocol, *args: Any, **kwargs: Any) -> None: ...


@runtime_checkable
class LinearSystemProblemProtocol(Protocol):
    name: str


@runtime_checkable
class BackendAdapterProtocol(Protocol):
    name: str

    def run(self, circuit: Any, *args: Any, **kwargs: Any) -> Any: ...


class RegistryProtocol(Protocol[T]):
    def register(
        self,
        item_or_name: T | str,
        item: T | None = None,
        *,
        name: str | None = None,
        override: bool = False,
    ) -> None: ...

    def get(self, name: str) -> T: ...

    def has(self, name: str) -> bool: ...

    def names(self) -> list[str]: ...

    def all(self) -> list[T]: ...


class EncodingSelectorProtocol(Protocol):
    def select(self, data: Any) -> EncodingProtocol: ...

    def rank_candidates(self, data: Any) -> list[dict[str, Any]]: ...


class PipelineBuilderProtocol(Protocol):
    def with_data(self, value: Any, metadata: dict[str, Any] | None = None) -> "PipelineBuilderProtocol": ...

    def with_encoding(self, name: str) -> "PipelineBuilderProtocol": ...

    def auto_encoding(self) -> "PipelineBuilderProtocol": ...

    def with_metadata(self, **metadata: Any) -> "PipelineBuilderProtocol": ...

    def build(self) -> Any: ...

    def run(self) -> Any: ...


class MetricsCollectorProtocol(Protocol):
    def collect(self, circuit: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]: ...


class ResultProtocol(Protocol):
    raw: Any


class ResultHandler(Protocol):
    def handle(self, raw_result: Any) -> Any: ...


# Backward-compatible aliases.
EncodingHandler = EncodingProtocol
AlgorithmHandler = AlgorithmProtocol
BackendAdapter = BackendAdapterProtocol
