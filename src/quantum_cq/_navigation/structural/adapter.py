"""Explicit pipeline adapter for StructuralNavigationResult."""

from __future__ import annotations

from typing import Any

from quantum_cq._runtime.unified import PipelineInputAdapterDescriptor

from .models import StructuralNavigationError, StructuralNavigationResult


class StructuralNavigationInputAdapter:
    adapter_id = "navigation_v2_structural_result"
    navigation_version = "v2"
    engine_origin = "neutral"
    exactness = "exact"
    neutralizable = True
    limitations = (
        "aceita somente StructuralNavigationResult com CircuitIR materializado",
        "oracle_model abstrato nao pode seguir para compile/run fisicos",
    )

    def supports(self, value: Any) -> bool:
        return isinstance(value, StructuralNavigationResult)

    def adapt(self, value: Any, context: Any) -> Any:
        if not isinstance(value, StructuralNavigationResult):
            raise TypeError("StructuralNavigationInputAdapter espera StructuralNavigationResult")
        if value.circuit_format != "ir" or value.circuit is None:
            raise StructuralNavigationError(
                "StructuralNavigationResult nao possui CircuitIR materializado; "
                "lowering abstrato nao pode seguir para pipeline fisica"
            )
        return value.circuit

    def descriptor(self) -> PipelineInputAdapterDescriptor:
        return PipelineInputAdapterDescriptor(
            adapter_id=self.adapter_id,
            input_type="StructuralNavigationResult",
            features=(
                "structural_source",
                "validated_structure",
                "canonical_structure",
                "equivalence_class",
                "navigation_plan",
                "structural_operation",
                "semantic_verification",
                "logical_circuit",
            ),
            output_format="ir",
            navigation_version="v2",
            engine_origin="neutral",
            neutralizable=True,
            exactness="exact",
            limitations=self.limitations,
            provenance={"source": "navigation_v2"},
        )

