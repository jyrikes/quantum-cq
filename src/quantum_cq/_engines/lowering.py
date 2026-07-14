"""Minimal lowering rules shared by engine adapters."""

from __future__ import annotations

from dataclasses import replace

from quantum_cq._circuits.compact import CircuitIR, Layer, Operation
from quantum_cq._engines.capabilities import EngineCapabilities
from quantum_cq._engines.errors import CapabilityMismatchError


def lower_for_capabilities(ir: CircuitIR, capabilities: EngineCapabilities) -> CircuitIR:
    lowered_layers: list[Layer] = []

    for layer in ir.layers:
        lowered = Layer()
        for operation in layer.operations:
            for next_operation in _lower_operation(operation, capabilities):
                lowered.add(next_operation)
        lowered_layers.append(lowered)

    return replace(ir, layers=lowered_layers)


def _lower_operation(operation: Operation, capabilities: EngineCapabilities) -> tuple[Operation, ...]:
    if operation.kind != "mcx":
        if not capabilities.supports(operation.kind):
            raise CapabilityMismatchError(
                f"Engine '{capabilities.engine}' does not support operation '{operation.kind}'"
            )
        return (operation,)

    controls = tuple(operation.params.get("controls", operation.qubits[:-1]))
    target = int(operation.params.get("target", operation.qubits[-1]))

    if len(controls) == 0:
        return (Operation("x", qubits=(target,)),)

    if len(controls) == 1:
        control = int(controls[0])
        return (
            Operation(
                "cx",
                qubits=(control, target),
                params={"control": control, "target": target},
            ),
        )

    if len(controls) == 2:
        if capabilities.supports("ccx"):
            return (Operation("ccx", qubits=(int(controls[0]), int(controls[1]), target)),)
        if capabilities.supports("mcx"):
            return (operation,)
        raise CapabilityMismatchError(
            f"Engine '{capabilities.engine}' does not support two-control MCX"
        )

    if capabilities.status("mcx") == "supported":
        return (operation,)

    raise CapabilityMismatchError(
        f"Engine '{capabilities.engine}' does not support MCX with {len(controls)} controls"
    )
