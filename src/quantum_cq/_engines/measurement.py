"""Canonical measurement contract for the multi-engine layer."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from quantum_cq._circuits.compact import CircuitIR, Operation


MeasurementPolicy = Literal["auto", "preserve", "all", "none"]


@dataclass(frozen=True)
class MeasurementMapping:
    qubit: int
    clbit: int
    source: str = "explicit"


@dataclass(frozen=True)
class MeasurementContract:
    n_qubits: int
    n_clbits: int
    explicit_mappings: tuple[MeasurementMapping, ...] = ()
    effective_mappings: tuple[MeasurementMapping, ...] = ()
    policy: MeasurementPolicy = "preserve"
    explicit: bool = False
    automatic: bool = False
    materialized: bool = False
    implicit_native: bool = False
    measured_qubits: tuple[int, ...] = ()
    logical_clbits: tuple[int, ...] = ()
    native_positions: tuple[int, ...] = ()
    canonical_bit_order: tuple[int, ...] = ()
    native_bit_order: tuple[int, ...] = ()
    endianness: str = "clbit-desc"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        effective = tuple(self.effective_mappings)
        explicit = tuple(self.explicit_mappings)
        measured_qubits = self.measured_qubits or tuple(mapping.qubit for mapping in effective)
        logical_clbits = self.logical_clbits or tuple(mapping.clbit for mapping in effective)
        canonical = self.canonical_bit_order or _canonical_order(effective)
        native_order = self.native_bit_order or tuple(mapping.clbit for mapping in effective)
        native_positions = self.native_positions or tuple(range(len(native_order)))
        object.__setattr__(self, "explicit_mappings", explicit)
        object.__setattr__(self, "effective_mappings", effective)
        object.__setattr__(self, "measured_qubits", tuple(measured_qubits))
        object.__setattr__(self, "logical_clbits", tuple(logical_clbits))
        object.__setattr__(self, "native_positions", tuple(native_positions))
        object.__setattr__(self, "canonical_bit_order", tuple(canonical))
        object.__setattr__(self, "native_bit_order", tuple(native_order))
        object.__setattr__(self, "notes", tuple(self.notes))

    def with_native_order(
        self,
        native_bit_order: tuple[int, ...],
        *,
        implicit_native: bool | None = None,
        materialized: bool | None = None,
        note: str | None = None,
    ) -> "MeasurementContract":
        notes = self.notes if note is None else (*self.notes, note)
        return replace(
            self,
            native_bit_order=native_bit_order,
            implicit_native=self.implicit_native if implicit_native is None else implicit_native,
            materialized=self.materialized if materialized is None else materialized,
            notes=notes,
        )

    def to_metadata(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "explicit": self.explicit,
            "automatic": self.automatic,
            "materialized": self.materialized,
            "implicit_native": self.implicit_native,
            "mappings": tuple((m.qubit, m.clbit, m.source) for m in self.effective_mappings),
            "measured_qubits": self.measured_qubits,
            "logical_clbits": self.logical_clbits,
            "native_positions": self.native_positions,
            "canonical_bit_order": self.canonical_bit_order,
            "native_bit_order": self.native_bit_order,
            "endianness": self.endianness,
            "notes": self.notes,
        }


def measurement_contract_from_ir(
    ir: CircuitIR,
    *,
    policy: MeasurementPolicy = "preserve",
) -> MeasurementContract:
    explicit = tuple(_measurement_mappings(ir, source="explicit"))
    return _contract(
        ir,
        explicit_mappings=explicit,
        effective_mappings=explicit,
        policy=policy,
        automatic=False,
        materialized=bool(explicit),
    )


def prepare_ir_for_execution(
    ir: CircuitIR,
    *,
    policy: MeasurementPolicy = "auto",
) -> tuple[CircuitIR, MeasurementContract]:
    explicit = tuple(_measurement_mappings(ir, source="explicit"))
    if explicit:
        return ir, _contract(
            ir,
            explicit_mappings=explicit,
            effective_mappings=explicit,
            policy=policy,
            automatic=False,
            materialized=True,
        )

    if policy not in {"auto", "all"}:
        return ir, _contract(
            ir,
            explicit_mappings=(),
            effective_mappings=(),
            policy=policy,
            automatic=False,
            materialized=False,
        )

    mappings = tuple(MeasurementMapping(qubit=q, clbit=q, source="auto") for q in range(ir.n_qubits))
    outputs = [
        *ir.outputs,
        *(Operation("measure", qubits=(m.qubit,), clbits=(m.clbit,)) for m in mappings),
    ]
    measured = replace(ir, n_clbits=max(ir.n_clbits, ir.n_qubits), outputs=outputs)
    return measured, _contract(
        measured,
        explicit_mappings=(),
        effective_mappings=mappings,
        policy=policy,
        automatic=True,
        materialized=True,
        note="measure-all automatico aplicado por CQ.run_engine",
    )


def measure_all_contract(n_qubits: int, *, policy: MeasurementPolicy = "auto") -> MeasurementContract:
    mappings = tuple(MeasurementMapping(qubit=q, clbit=q, source="auto") for q in range(n_qubits))
    return MeasurementContract(
        n_qubits=n_qubits,
        n_clbits=n_qubits,
        effective_mappings=mappings,
        policy=policy,
        automatic=True,
        materialized=True,
        canonical_bit_order=_canonical_order(mappings),
        native_bit_order=tuple(range(n_qubits)),
        notes=("measure-all automatico aplicado por CQ.run_engine",),
    )


def empty_contract(n_qubits: int, n_clbits: int = 0) -> MeasurementContract:
    return MeasurementContract(n_qubits=n_qubits, n_clbits=n_clbits)


def canonical_counts_from_rows(
    rows: list[list[int]] | tuple[tuple[int, ...], ...],
    mappings: tuple[MeasurementMapping, ...],
) -> dict[str, int]:
    if not mappings:
        return {}

    clbits_by_column = tuple(mapping.clbit for mapping in mappings)
    canonical_clbits = sorted(clbits_by_column, reverse=True)
    counts: dict[str, int] = {}
    for row in rows:
        values = {clbit: int(row[index]) for index, clbit in enumerate(clbits_by_column)}
        bitstring = "".join(str(values[clbit]) for clbit in canonical_clbits)
        counts[bitstring] = counts.get(bitstring, 0) + 1
    return counts


def _measurement_mappings(ir: CircuitIR, *, source: str) -> list[MeasurementMapping]:
    mappings: list[MeasurementMapping] = []
    for layer in ir.layers:
        for operation in layer.operations:
            if operation.kind == "measure":
                mappings.append(
                    MeasurementMapping(
                        qubit=int(operation.qubits[0]),
                        clbit=int(operation.clbits[0]),
                        source=source,
                    )
                )
    for operation in ir.outputs:
        if operation.kind == "measure":
            mappings.append(
                MeasurementMapping(
                    qubit=int(operation.qubits[0]),
                    clbit=int(operation.clbits[0]),
                    source=source,
                )
            )
    return mappings


def _contract(
    ir: CircuitIR,
    *,
    explicit_mappings: tuple[MeasurementMapping, ...],
    effective_mappings: tuple[MeasurementMapping, ...],
    policy: MeasurementPolicy,
    automatic: bool,
    materialized: bool,
    note: str | None = None,
) -> MeasurementContract:
    notes = () if note is None else (note,)
    return MeasurementContract(
        n_qubits=ir.n_qubits,
        n_clbits=ir.n_clbits,
        explicit_mappings=explicit_mappings,
        effective_mappings=effective_mappings,
        policy=policy,
        explicit=bool(explicit_mappings),
        automatic=automatic,
        materialized=materialized,
        canonical_bit_order=_canonical_order(effective_mappings),
        native_bit_order=tuple(mapping.clbit for mapping in effective_mappings),
        notes=notes,
    )


def _canonical_order(mappings: tuple[MeasurementMapping, ...]) -> tuple[int, ...]:
    return tuple(sorted((mapping.clbit for mapping in mappings), reverse=True))
