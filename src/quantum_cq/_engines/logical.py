"""Helpers for the existing logical CircuitIR."""

from __future__ import annotations

from typing import Any

from quantum_cq._circuits.compact import CircuitIR, CompactAdapter, QC
from quantum_cq._core.results import AlgorithmCircuit, EncodedCircuit, NavigationCircuit, OperatorCircuit, OracleCircuit
from quantum_cq._engines.errors import EmissionError


def to_logical_ir(circuit_like: Any) -> CircuitIR:
    if isinstance(circuit_like, CircuitIR):
        return circuit_like

    if isinstance(circuit_like, QC):
        return CompactAdapter().parse(circuit_like)

    if isinstance(circuit_like, (AlgorithmCircuit, OperatorCircuit, OracleCircuit, NavigationCircuit)):
        if circuit_like.circuit_format != "ir":
            raise EmissionError(
                f"{type(circuit_like).__name__} with circuit_format='{circuit_like.circuit_format}' "
                "cannot be emitted to optional engines without a logical CircuitIR"
            )
        return to_logical_ir(circuit_like.circuit)

    if isinstance(circuit_like, EncodedCircuit):
        return to_logical_ir(circuit_like.circuit)

    raise EmissionError(
        f"Engine emission expects QC or CircuitIR, got {type(circuit_like).__name__}"
    )


def iter_operations(ir: CircuitIR):
    for layer in ir.layers:
        for operation in layer.operations:
            yield operation
    yield from ir.outputs
