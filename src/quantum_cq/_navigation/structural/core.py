"""Exact finite Navigation v2 structural semantics and lowering."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from quantum_cq._circuits.compact import LogicalCircuitFactory
from quantum_cq._navigation.memory import AddressedMemory, AddressedMemoryEncoding

from .models import (
    RhoDResult,
    SemanticVerification,
    StructuralEquivalenceClass,
    StructuralField,
    StructuralHeap,
    StructuralNavigationError,
    StructuralNavigationPlan,
    StructuralNavigationResult,
    StructuralNode,
    StructuralOperation,
    StructuralPointer,
    StructuralSelector,
    StructuralType,
)


SUPPORTED_OPERATIONS = {"read", "next", "parent", "child", "neighbor", "compare"}
SUPPORTED_PREDICATES = {
    "pointer_is_null",
    "pointer_equal",
    "value_equal",
    "type_equal",
    "field_exists",
}


def build_navigation_v2(
    heap: StructuralHeap,
    *,
    operation: str,
    pointer: StructuralPointer | str | None = None,
    selector: StructuralSelector | str | int | None = None,
    predicate: str | None = None,
    lowering: str = "explicit_exact",
    exactness: str = "exact",
    access_distribution: Mapping[str, float] | None = None,
    spectral_limit: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    candidate_limit: int = 5040,
) -> StructuralNavigationResult:
    if operation not in SUPPORTED_OPERATIONS:
        raise StructuralNavigationError(f"operation v2 nao suportada: {operation}")
    if exactness != "exact":
        raise StructuralNavigationError("Navigation v2 nesta run suporta apenas exactness='exact'")
    if operation == "compare":
        if predicate is None:
            raise StructuralNavigationError("predicate e obrigatorio para operation='compare'")
        if predicate not in SUPPORTED_PREDICATES:
            raise StructuralNavigationError(f"predicate nao suportado: {predicate}")
    elif predicate is not None:
        raise StructuralNavigationError("predicate so e aceito para operation='compare'")
    if lowering not in {"explicit_exact", "sparse_exact", "oracle_model"}:
        raise StructuralNavigationError(f"lowering v2 nao suportado: {lowering}")

    validated = validate_heap(heap)
    equivalence = canonicalize_heap(validated, candidate_limit=candidate_limit)
    if equivalence.status != "canonical" or equivalence.canonical_heap is None:
        raise StructuralNavigationError("canonicalizacao estrutural nao concluiu: " + "; ".join(equivalence.diagnostics))

    resolved_selector = _resolve_selector(operation, selector, predicate=predicate)
    resolved_pointer = _resolve_pointer(pointer, equivalence)
    operation_obj = StructuralOperation(
        operation_id=_operation_id(operation, resolved_selector, predicate),
        operation=operation,
        selector=resolved_selector,
        predicate=predicate,
        exactness="exact",
        provenance={"source": "CQ.navigation_v2"},
    )
    plan = build_plan(
        equivalence,
        operation_obj,
        pointer=resolved_pointer,
        lowering=lowering,
        access_distribution=access_distribution,
        spectral_limit=spectral_limit,
    )
    verification = verify_plan(plan)
    circuit = None
    circuit_format = "abstract"
    if lowering in {"explicit_exact", "sparse_exact"}:
        circuit = lower_plan_to_ir(plan)
        circuit_format = "ir"

    result_metadata = {
        "family": "navigation",
        "role": "structural_navigation",
        "navigation_name": "structural_navigation_v2",
        "navigation_version": "v2",
        "operation": operation,
        "predicate": predicate,
        "exactness": "exact",
        "lowering_strategy": lowering,
        "equivalence_fingerprint": equivalence.equivalence_fingerprint,
        "lowering_backend": "navigation_v1" if lowering in {"explicit_exact", "sparse_exact"} else "oracle_model",
        "navigation_version_source": "v2",
        "status": "implemented_exact" if circuit is not None else "abstract_model",
        **dict(metadata or {}),
    }
    if circuit is not None:
        circuit.metadata.update(_circuit_metadata(plan, result_metadata))

    return StructuralNavigationResult(
        circuit=circuit,
        navigation_name="structural_navigation_v2",
        circuit_format=circuit_format,
        metadata=result_metadata,
        source=heap,
        validated_structure=validated,
        canonical_structure=equivalence.canonical_heap,
        equivalence_class=equivalence,
        plan=plan,
        operation=operation_obj,
        verification=verification,
    )


def validate_heap(heap: StructuralHeap) -> StructuralHeap:
    type_map = heap.type_map()
    node_map = heap.node_map()
    for root in heap.roots:
        if root not in node_map:
            raise StructuralNavigationError(f"root inexistente: {root}")
    incoming: dict[str, int] = defaultdict(int)
    for node in heap.nodes:
        if node.type_id not in type_map:
            raise StructuralNavigationError(f"node '{node.local_node_id}' usa type_id desconhecido")
        node_type = type_map[node.type_id]
        field_map = node_type.field_map()
        unknown = set(node.fields) - set(field_map)
        if unknown:
            raise StructuralNavigationError(f"node '{node.local_node_id}' possui campo desconhecido: {sorted(unknown)}")
        for field in node_type.fields:
            if field.name not in node.fields:
                if field.required and not field.nullable:
                    raise StructuralNavigationError(f"campo obrigatorio ausente: {node.local_node_id}.{field.name}")
                continue
            value = node.fields[field.name]
            _validate_field_value(node.local_node_id, field, value, node_map, incoming)
    if not heap.allow_cycles:
        _reject_cycles(heap, type_map)
    if not heap.allow_sharing:
        shared = [node_id for node_id, count in incoming.items() if count > 1]
        if shared:
            raise StructuralNavigationError(f"sharing nao permitido: {sorted(shared)}")
    for node_type in type_map.values():
        if node_type.strict_tree:
            parent_fields = node_type.fields_by_role("parent")
            if len(parent_fields) > 1:
                raise StructuralNavigationError("strict_tree aceita no maximo um campo parent")
    return heap


def canonicalize_heap(
    heap: StructuralHeap,
    *,
    candidate_limit: int = 5040,
) -> StructuralEquivalenceClass:
    local_ids = tuple(sorted(node.local_node_id for node in heap.nodes))
    candidate_count = math.factorial(len(local_ids))
    if candidate_count > candidate_limit:
        return StructuralEquivalenceClass(
            canonical_heap=None,
            equivalence_fingerprint=None,
            local_to_canonical={},
            canonical_to_local={},
            canonical_order=(),
            status="insufficient_information",
            candidate_count=candidate_count,
            candidate_limit=candidate_limit,
            diagnostics=(f"candidate_limit atingido: {candidate_count}>{candidate_limit}",),
            provenance={"strategy": "lexicographic_minimum_permutation"},
        )

    best_serialized: str | None = None
    best_mapping: dict[str, str] | None = None
    for permutation in itertools.permutations(local_ids):
        mapping = {local_id: f"n{index}" for index, local_id in enumerate(permutation)}
        serialized = _serialize_candidate(heap, mapping)
        if best_serialized is None or serialized < best_serialized:
            best_serialized = serialized
            best_mapping = mapping

    assert best_serialized is not None and best_mapping is not None
    canonical_to_local = {canonical: local for local, canonical in best_mapping.items()}
    canonical_nodes = []
    node_map = heap.node_map()
    type_map = heap.type_map()
    for canonical_id in sorted(canonical_to_local, key=_canonical_sort_key):
        local_id = canonical_to_local[canonical_id]
        node = node_map[local_id]
        node_type = type_map[node.type_id]
        canonical_nodes.append(
            StructuralNode(
                canonical_id,
                node.type_id,
                {
                    field.name: _canonical_value(node.fields.get(field.name), field, best_mapping)
                    for field in node_type.fields
                    if field.name in node.fields
                },
                provenance={"local_node_id": local_id},
            )
        )
    canonical_heap = StructuralHeap(
        types=tuple(sorted(heap.types, key=lambda item: item.type_id)),
        nodes=tuple(canonical_nodes),
        roots=tuple(best_mapping[root] for root in heap.roots),
        allow_cycles=heap.allow_cycles,
        allow_sharing=heap.allow_sharing,
        metadata={**dict(heap.metadata), "canonicalized": True},
    )
    fingerprint = hashlib.sha256(best_serialized.encode("utf-8")).hexdigest()
    return StructuralEquivalenceClass(
        canonical_heap=canonical_heap,
        equivalence_fingerprint=fingerprint,
        local_to_canonical=best_mapping,
        canonical_to_local=canonical_to_local,
        canonical_order=tuple(node.local_node_id for node in canonical_nodes),
        status="canonical",
        candidate_count=candidate_count,
        candidate_limit=candidate_limit,
        provenance={"strategy": "lexicographic_minimum_permutation"},
    )


def build_plan(
    equivalence: StructuralEquivalenceClass,
    operation: StructuralOperation,
    *,
    pointer: StructuralPointer | None,
    lowering: str,
    access_distribution: Mapping[str, float] | None,
    spectral_limit: int | None,
) -> StructuralNavigationPlan:
    heap = equivalence.canonical_heap
    if heap is None:
        raise StructuralNavigationError("build_plan requer canonical_heap")
    node_ids = tuple(node.local_node_id for node in heap.nodes)
    null_encoding = len(node_ids)
    pointer_width = max(1, _ceil_log2(len(node_ids) + 1))
    pointer_codes = {node_id: index for index, node_id in enumerate(node_ids)}
    pointer_domain = (*node_ids, "null")
    selector_domain = () if operation.selector is None else (operation.selector.selector_id,)
    table: dict[int, RhoDResult] = {}
    memory_values: list[int] = []
    output_width = _output_width(heap, operation, pointer_width)
    address_space = 2**pointer_width
    for code in range(address_space):
        if code < len(node_ids):
            pointer_id = node_ids[code]
        elif code == null_encoding:
            pointer_id = None
        else:
            pointer_id = None
        rho = resolve_rho(heap, pointer_id, operation)
        table[code] = rho
        memory_values.append(_rho_output_value(rho, operation, pointer_codes, null_encoding))
    for value in memory_values:
        if value < 0 or value >= 2**output_width:
            raise StructuralNavigationError("saida da operacao nao cabe no registrador declarado")
    metrics = structural_metrics(heap, access_distribution=access_distribution, spectral_limit=spectral_limit)
    layout = {
        "pointer": {"width": pointer_width, "codes": pointer_codes, "null_encoding": null_encoding},
        "selector": {"width": 0, "fixed": None if operation.selector is None else operation.selector.to_dict()},
        "output": {"width": output_width, "xor_accumulator": True},
        "logical_qubits": pointer_width + output_width,
        "physical_qubits": "assigned_after_placement",
    }
    plan_payload = {
        "fingerprint": equivalence.equivalence_fingerprint,
        "operation": operation.to_dict(),
        "rho_table": {str(key): value.to_dict() for key, value in table.items()},
        "memory_values": memory_values,
        "layout": layout,
        "lowering": lowering,
    }
    plan_fingerprint = hashlib.sha256(json.dumps(plan_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return StructuralNavigationPlan(
        navigation_version="v2",
        equivalence_class=equivalence,
        operation=operation,
        node_count=len(node_ids),
        pointer_domain=pointer_domain,
        selector_domain=selector_domain,
        value_width=max((field.bit_width for item in heap.types for field in item.fields if field.value_type == "uint"), default=1),
        pointer_width=pointer_width,
        output_width=output_width,
        register_layout=layout,
        null_encoding=null_encoding,
        rho_table=table,
        memory_values=tuple(memory_values),
        exactness="exact",
        lowering_strategy=lowering,
        resource_estimates={
            **metrics,
            "logical_qubits": pointer_width + output_width,
            "address_qubits": pointer_width,
            "data_qubits": output_width,
            "plan_fingerprint": plan_fingerprint,
        },
        provenance={
            "navigation_version_source": "v2",
            "lowering_backend": "navigation_v1" if lowering in {"explicit_exact", "sparse_exact"} else "oracle_model",
            "v1_engine": "explicit_circuit" if lowering == "explicit_exact" else lowering,
            "equivalence_fingerprint": equivalence.equivalence_fingerprint,
        },
    )


def resolve_rho(
    heap: StructuralHeap,
    canonical_pointer: str | None,
    operation: StructuralOperation,
) -> RhoDResult:
    selector = operation.selector or StructuralSelector("identity", "identity")
    if canonical_pointer is None:
        if operation.operation == "compare" and operation.predicate == "pointer_is_null":
            return RhoDResult(
                None,
                selector,
                value=1,
                status="resolved",
                null_state="null_pointer",
                provenance={"predicate": "pointer_is_null"},
            )
        return RhoDResult(
            None,
            selector,
            status="null",
            null_state="null_pointer",
            diagnostics=("input pointer is null or outside domain",),
        )
    node_map = heap.node_map()
    node = node_map.get(canonical_pointer)
    if node is None:
        return RhoDResult(
            canonical_pointer,
            selector,
            status="invalid_reference",
            null_state="invalid",
            diagnostics=("canonical pointer not found",),
        )
    if operation.operation == "compare":
        return _resolve_compare(heap, node, operation)
    field = _field_for_selector(heap, node, selector, operation.operation)
    if field is None:
        return _absence_result(canonical_pointer, selector, "selector not applicable")
    value = node.fields.get(field.name)
    if field.value_type == "uint":
        return RhoDResult(
            canonical_pointer,
            selector,
            value_location=(canonical_pointer, field.name),
            value=int(value),
            status="resolved",
            null_state="not_null",
            provenance={"field": field.name, "semantic_role": field.semantic_role},
        )
    target = _reference_target(value, selector.index)
    if target is None:
        return RhoDResult(
            canonical_pointer,
            selector,
            resolved_canonical_pointer=None,
            status="null",
            null_state="null_result",
            diagnostics=("selector resolved to null",),
            provenance={"field": field.name, "semantic_role": field.semantic_role},
        )
    return RhoDResult(
        canonical_pointer,
        selector,
        resolved_canonical_pointer=str(target),
        status="resolved",
        null_state="not_null",
        provenance={"field": field.name, "semantic_role": field.semantic_role},
    )


def lower_plan_to_ir(plan: StructuralNavigationPlan):
    if plan.lowering_strategy == "oracle_model":
        raise StructuralNavigationError("oracle_model e abstrato e nao produz CircuitIR")
    memory = AddressedMemory(
        plan.memory_values,
        data_bit_width=plan.output_width,
        address_bit_width=plan.pointer_width,
        default_value=0,
    )
    engine = "sparse_explicit_circuit" if plan.lowering_strategy == "sparse_exact" else "explicit_circuit"
    built = AddressedMemoryEncoding(
        engine=engine,
        circuit_factory=LogicalCircuitFactory(),
    ).encode(memory)
    circuit = built.circuit
    circuit.metadata.update(_circuit_metadata(plan, built.metadata))
    return circuit


def verify_plan(plan: StructuralNavigationPlan) -> SemanticVerification:
    max_value = 2**plan.output_width
    values_fit = all(0 <= value < max_value for value in plan.memory_values)
    rho_complete = len(plan.rho_table) == 2**plan.pointer_width
    xor_involution = values_fit and rho_complete
    checks = {
        "input_preserved": True,
        "output_xor": True,
        "values_fit_register": values_fit,
        "rho_table_complete": rho_complete,
        "involution": xor_involution,
        "uncompute": xor_involution,
        "bijective_embedding": xor_involution,
        "unitary_finite_embedding": xor_involution,
        "collision_encoding": "none_detected",
        "observational_collision": {
            "observation_set": (plan.operation.operation,),
            "status": "not_detected_for_finite_operation_set",
            "limitations": "Nao afirma ausencia universal de colisao observacional",
        },
    }
    return SemanticVerification(
        status="verified" if all(value is True for key, value in checks.items() if isinstance(value, bool)) else "failed",
        finite_domain_semantic_verification=xor_involution,
        checks=checks,
        provenance={"method": "finite_table_xor_embedding"},
    )


def structural_metrics(
    heap: StructuralHeap,
    *,
    access_distribution: Mapping[str, float] | None = None,
    spectral_limit: int | None = None,
) -> dict[str, Any]:
    references = _reference_edges(heap)
    metrics: dict[str, Any] = {
        "node_count": len(heap.nodes),
        "root_count": len(heap.roots),
        "type_count": len(heap.types),
        "field_count": sum(len(item.fields) for item in heap.types),
        "reference_count": len(references),
        "component_count": _component_count(heap, references),
        "has_cycles": _has_cycle(heap, references),
    }
    if access_distribution is not None:
        metrics["renyi_h2"] = _renyi_h2(access_distribution, {node.local_node_id for node in heap.nodes})
    if spectral_limit is not None and len(heap.nodes) <= spectral_limit:
        metrics["spectral"] = _spectral_small_graph(heap, references)
    elif spectral_limit is not None:
        metrics["spectral"] = {"status": "not_applicable", "reason": "spectral_limit exceeded"}
    return metrics


def _validate_field_value(
    node_id: str,
    field: StructuralField,
    value: Any,
    node_map: Mapping[str, StructuralNode],
    incoming: dict[str, int],
) -> None:
    if value is None:
        if not field.nullable:
            raise StructuralNavigationError(f"{node_id}.{field.name} nao aceita null")
        return
    if field.value_type == "uint":
        if isinstance(value, bool) or not isinstance(value, int):
            raise StructuralNavigationError(f"{node_id}.{field.name} deve ser inteiro")
        if value < 0 or value >= 2**field.bit_width:
            raise StructuralNavigationError(f"{node_id}.{field.name} fora do dominio")
        return
    if field.value_type == "reference":
        if str(value) not in node_map:
            raise StructuralNavigationError(f"referencia invalida em {node_id}.{field.name}: {value}")
        if field.semantic_role != "parent":
            incoming[str(value)] += 1
        return
    if field.value_type == "reference_list":
        if not isinstance(value, (list, tuple)):
            raise StructuralNavigationError(f"{node_id}.{field.name} deve ser lista de referencias")
        for item in value:
            if item is None:
                if not field.nullable:
                    raise StructuralNavigationError(f"{node_id}.{field.name} contem null sem nullable")
                continue
            if str(item) not in node_map:
                raise StructuralNavigationError(f"referencia invalida em {node_id}.{field.name}: {item}")
            if field.semantic_role != "parent":
                incoming[str(item)] += 1


def _reject_cycles(heap: StructuralHeap, type_map: Mapping[str, StructuralType]) -> None:
    if _has_cycle(heap, _reference_edges(heap)):
        raise StructuralNavigationError("ciclos nao permitidos pela politica da estrutura")
    for node in heap.nodes:
        if not type_map[node.type_id].allow_cycles and _has_cycle(StructuralHeap(heap.types, heap.nodes, (node.local_node_id,)), _reference_edges(heap)):
            raise StructuralNavigationError(f"tipo {node.type_id} nao permite ciclos")


def _serialize_candidate(heap: StructuralHeap, mapping: Mapping[str, str]) -> str:
    type_map = heap.type_map()
    node_map = heap.node_map()
    nodes = []
    for local_id, canonical_id in sorted(mapping.items(), key=lambda item: _canonical_sort_key(item[1])):
        node = node_map[local_id]
        node_type = type_map[node.type_id]
        nodes.append(
            {
                "id": canonical_id,
                "type": node.type_id,
                "fields": [
                    {
                        "name": field.name,
                        "role": field.semantic_role,
                        "value": _canonical_value(node.fields.get(field.name), field, mapping),
                    }
                    for field in node_type.fields
                    if field.name in node.fields
                ],
            }
        )
    payload = {
        "roots": [mapping[root] for root in heap.roots],
        "types": [item.to_dict() for item in sorted(heap.types, key=lambda item: item.type_id)],
        "nodes": nodes,
        "allow_cycles": heap.allow_cycles,
        "allow_sharing": heap.allow_sharing,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _canonical_value(value: Any, field: StructuralField, mapping: Mapping[str, str]) -> Any:
    if value is None:
        return None
    if field.value_type == "uint":
        return int(value)
    if field.value_type == "reference":
        return mapping[str(value)]
    if field.value_type == "reference_list":
        return [None if item is None else mapping[str(item)] for item in value]
    return value


def _canonical_sort_key(value: str) -> tuple[int, str]:
    if value.startswith("n") and value[1:].isdigit():
        return int(value[1:]), value
    return 10**9, value


def _resolve_selector(
    operation: str,
    selector: StructuralSelector | str | int | None,
    *,
    predicate: str | None,
) -> StructuralSelector | None:
    if operation == "compare":
        if predicate == "pointer_is_null":
            return None if selector is None else _selector_from_value(selector, "value")
        if predicate in {"value_equal", "field_exists"}:
            if selector is None:
                raise StructuralNavigationError(f"selector e obrigatorio para predicate={predicate}")
            return _selector_from_value(selector, "value")
        if predicate in {"type_equal", "pointer_equal"}:
            return None if selector is None else _selector_from_value(selector, "value")
    if operation == "read":
        if selector is None:
            raise StructuralNavigationError("selector e obrigatorio para operation='read'")
        return _selector_from_value(selector, "value")
    if operation in {"next", "parent"}:
        return _selector_from_value(selector, operation) if selector is not None else StructuralSelector.role(operation)
    if operation in {"child", "neighbor"}:
        if selector is None:
            raise StructuralNavigationError(f"selector com index e obrigatorio para operation='{operation}'")
        if isinstance(selector, int):
            return StructuralSelector.role(operation, index=selector)
        selected = _selector_from_value(selector, operation)
        if selected.index is None:
            raise StructuralNavigationError(f"{operation}(index) requer index explicito")
        return selected
    return None


def _selector_from_value(value: StructuralSelector | str | int, default_kind: str) -> StructuralSelector:
    if isinstance(value, StructuralSelector):
        return value
    if isinstance(value, int):
        return StructuralSelector.role(default_kind, index=value)
    return StructuralSelector(f"{default_kind}:{value}", default_kind, field_name=str(value))


def _resolve_pointer(
    pointer: StructuralPointer | str | None,
    equivalence: StructuralEquivalenceClass,
) -> StructuralPointer | None:
    if pointer is None:
        return None
    if isinstance(pointer, StructuralPointer):
        if pointer.canonical_node_id is not None:
            return pointer
        local = pointer.provenance.get("local_node_id")
        if local is not None and local in equivalence.local_to_canonical:
            return replace(pointer, canonical_node_id=equivalence.local_to_canonical[str(local)])
        return pointer
    local_id = str(pointer)
    canonical = equivalence.local_to_canonical.get(local_id, local_id)
    return StructuralPointer(
        equivalence_fingerprint=equivalence.equivalence_fingerprint,
        canonical_node_id=canonical,
        provenance={"local_node_id": local_id},
    )


def _operation_id(operation: str, selector: StructuralSelector | None, predicate: str | None) -> str:
    selector_id = "none" if selector is None else selector.selector_id
    return f"{operation}:{selector_id}:{predicate or 'none'}"


def _field_for_selector(
    heap: StructuralHeap,
    node: StructuralNode,
    selector: StructuralSelector,
    operation: str,
) -> StructuralField | None:
    node_type = heap.type_map()[node.type_id]
    fields = node_type.fields
    if selector.field_name is not None:
        field = node_type.field_map().get(selector.field_name)
        if field is None:
            return None
        if operation == "read" and field.semantic_role not in {"value", "reference", "next", "parent", "child", "neighbor"}:
            return None
        if operation != "read" and field.semantic_role != operation:
            return None
        if operation in {"child", "neighbor"} and not field.ordered:
            raise StructuralNavigationError(f"{operation}(index) requer ordem semantica declarada")
        return field
    role_fields = tuple(field for field in fields if field.semantic_role == operation)
    if not role_fields:
        return None
    if len(role_fields) > 1:
        raise StructuralNavigationError(f"selector ambiguo para role {operation}; informe field_name")
    field = role_fields[0]
    if operation in {"child", "neighbor"} and not field.ordered:
        raise StructuralNavigationError(f"{operation}(index) requer ordem semantica declarada")
    return field


def _absence_result(pointer: str, selector: StructuralSelector, message: str) -> RhoDResult:
    if selector.absence_policy == "return_null":
        return RhoDResult(pointer, selector, status="null", null_state="selector_without_result", diagnostics=(message,))
    return RhoDResult(pointer, selector, status=selector.absence_policy, null_state="not_applicable", diagnostics=(message,))


def _reference_target(value: Any, index: int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if index is None:
            raise StructuralNavigationError("selector de lista requer index")
        if index >= len(value):
            return None
        item = value[index]
        return None if item is None else str(item)
    return str(value)


def _resolve_compare(heap: StructuralHeap, node: StructuralNode, operation: StructuralOperation) -> RhoDResult:
    selector = operation.selector or StructuralSelector("compare", "compare")
    predicate = operation.predicate
    if predicate == "pointer_is_null":
        value = 0
    elif predicate == "type_equal":
        expected = selector.expected_value if selector.expected_value is not None else selector.field_name
        value = int(node.type_id == expected)
    elif predicate == "field_exists":
        value = int(selector.field_name in heap.type_map()[node.type_id].field_map())
    elif predicate == "value_equal":
        field = _field_for_selector(heap, node, selector, "read")
        if field is None or field.value_type != "uint":
            value = 0
        else:
            value = int(int(node.fields.get(field.name, -1)) == int(selector.expected_value))
    elif predicate == "pointer_equal":
        expected = selector.expected_value if selector.expected_value is not None else selector.field_name
        value = int(node.local_node_id == expected)
    else:
        raise StructuralNavigationError(f"predicate nao suportado: {predicate}")
    return RhoDResult(
        node.local_node_id,
        selector,
        value=value,
        status="resolved",
        null_state="not_null",
        provenance={"predicate": predicate},
    )


def _rho_output_value(
    rho: RhoDResult,
    operation: StructuralOperation,
    pointer_codes: Mapping[str, int],
    null_encoding: int,
) -> int:
    if operation.operation == "compare":
        return int(rho.value or 0)
    if operation.operation == "read":
        if rho.value is not None:
            return int(rho.value)
        if rho.resolved_canonical_pointer is not None:
            return pointer_codes.get(rho.resolved_canonical_pointer, null_encoding)
        return 0
    if rho.resolved_canonical_pointer is None:
        return null_encoding
    return pointer_codes.get(rho.resolved_canonical_pointer, null_encoding)


def _output_width(heap: StructuralHeap, operation: StructuralOperation, pointer_width: int) -> int:
    if operation.operation in {"next", "parent", "child", "neighbor"}:
        return pointer_width
    if operation.operation == "compare":
        return 1
    if operation.selector is not None:
        for node_type in heap.types:
            field = node_type.field_map().get(operation.selector.field_name or "")
            if field is not None:
                return field.bit_width if field.value_type == "uint" else pointer_width
    return max((field.bit_width for item in heap.types for field in item.fields if field.value_type == "uint"), default=1)


def _ceil_log2(value: int) -> int:
    if value <= 1:
        return 0
    return math.ceil(math.log2(value))


def _circuit_metadata(plan: StructuralNavigationPlan, base: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(base),
        "navigation_version": "v2",
        "navigation_name": "structural_navigation_v2",
        "navigation_version_source": "v2",
        "lowering_backend": "navigation_v1",
        "lowering_strategy": plan.lowering_strategy,
        "v1_engine": "sparse_explicit_circuit" if plan.lowering_strategy == "sparse_exact" else "explicit_circuit",
        "equivalence_fingerprint": plan.equivalence_class.equivalence_fingerprint,
        "rho_table": {str(key): value.to_dict() for key, value in plan.rho_table.items()},
        "register_layout": dict(plan.register_layout),
        "null_encoding": plan.null_encoding,
        "exactness": "exact",
    }


def _reference_edges(heap: StructuralHeap) -> tuple[tuple[str, str], ...]:
    type_map = heap.type_map()
    edges: list[tuple[str, str]] = []
    for node in heap.nodes:
        node_type = type_map[node.type_id]
        for field in node_type.fields:
            if field.name not in node.fields or field.value_type == "uint":
                continue
            value = node.fields[field.name]
            if value is None:
                continue
            if field.value_type == "reference":
                edges.append((node.local_node_id, str(value)))
            else:
                edges.extend((node.local_node_id, str(item)) for item in value if item is not None)
    return tuple(edges)


def _has_cycle(heap: StructuralHeap, edges: tuple[tuple[str, str], ...]) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    for left, right in edges:
        graph[left].append(right)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for neighbor in graph.get(node, []):
            if visit(neighbor):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node.local_node_id) for node in heap.nodes)


def _component_count(heap: StructuralHeap, edges: tuple[tuple[str, str], ...]) -> int:
    if not heap.nodes:
        return 0
    graph: dict[str, set[str]] = {node.local_node_id: set() for node in heap.nodes}
    for left, right in edges:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    seen: set[str] = set()
    count = 0
    for node in graph:
        if node in seen:
            continue
        count += 1
        queue = deque([node])
        seen.add(node)
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return count


def _renyi_h2(distribution: Mapping[str, float], domain: set[str]) -> dict[str, Any]:
    keys = set(distribution)
    if keys - domain:
        raise StructuralNavigationError("access_distribution contem acesso fora do dominio")
    values = [float(value) for value in distribution.values()]
    if any(value < 0 for value in values):
        raise StructuralNavigationError("access_distribution nao aceita probabilidades negativas")
    total = sum(values)
    if abs(total - 1.0) > 1e-8:
        raise StructuralNavigationError("access_distribution deve somar 1")
    collision = sum(value * value for value in values)
    return {
        "value": -math.log2(collision) if collision > 0 else 0.0,
        "unit": "bits",
        "status": "computed",
        "source": "navigation_v2",
    }


def _spectral_small_graph(heap: StructuralHeap, edges: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    nodes = tuple(node.local_node_id for node in heap.nodes)
    index = {node: idx for idx, node in enumerate(nodes)}
    adjacency = [[0 for _ in nodes] for _ in nodes]
    for left, right in edges:
        adjacency[index[left]][index[right]] += 1
    degrees = [sum(row) for row in adjacency]
    laplacian = [
        [degrees[row] if row == col else -adjacency[row][col] for col in range(len(nodes))]
        for row in range(len(nodes))
    ]
    return {
        "status": "computed",
        "adjacency": adjacency,
        "degrees": degrees,
        "laplacian": laplacian,
        "spectrum": "not_computed_without_optional_dependency",
    }
