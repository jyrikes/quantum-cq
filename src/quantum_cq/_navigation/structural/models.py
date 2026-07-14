"""SDK-free structural navigation v2 data contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal


SemanticRole = Literal["value", "reference", "next", "parent", "child", "neighbor"]
FieldValueType = Literal["uint", "reference", "reference_list"]
AbsencePolicy = Literal["return_null", "incompatible", "failed"]

VALID_ROLES = {"value", "reference", "next", "parent", "child", "neighbor"}
VALID_VALUE_TYPES = {"uint", "reference", "reference_list"}
VALID_ABSENCE_POLICIES = {"return_null", "incompatible", "failed"}


class StructuralNavigationError(ValueError):
    """Raised when a Navigation v2 structure or operation is invalid."""


def _freeze_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _as_tuple(value: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(value or ())


@dataclass(frozen=True)
class StructuralField:
    name: str
    value_type: FieldValueType = "uint"
    bit_width: int = 1
    nullable: bool = False
    semantic_role: SemanticRole | None = None
    ordered: bool = True
    required: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise StructuralNavigationError("StructuralField.name nao pode ser vazio")
        if self.value_type not in VALID_VALUE_TYPES:
            raise StructuralNavigationError(f"value_type invalido: {self.value_type}")
        if self.semantic_role is not None and self.semantic_role not in VALID_ROLES:
            raise StructuralNavigationError(f"semantic_role invalido: {self.semantic_role}")
        if int(self.bit_width) <= 0:
            raise StructuralNavigationError("StructuralField.bit_width deve ser positivo")
        if self.value_type != "uint" and self.semantic_role == "value":
            raise StructuralNavigationError("semantic_role='value' requer value_type='uint'")
        if self.value_type == "uint" and self.semantic_role in {"next", "parent", "child", "neighbor", "reference"}:
            raise StructuralNavigationError("roles de referencia requerem campo de referencia")
        object.__setattr__(self, "bit_width", int(self.bit_width))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value_type": self.value_type,
            "bit_width": self.bit_width,
            "nullable": self.nullable,
            "semantic_role": self.semantic_role,
            "ordered": self.ordered,
            "required": self.required,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StructuralType:
    type_id: str
    fields: tuple[StructuralField, ...]
    allow_cycles: bool = True
    allow_sharing: bool = True
    strict_tree: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type_id:
            raise StructuralNavigationError("StructuralType.type_id nao pode ser vazio")
        fields = tuple(self.fields)
        names = [field.name for field in fields]
        if len(names) != len(set(names)):
            raise StructuralNavigationError(f"StructuralType '{self.type_id}' possui campos duplicados")
        if self.strict_tree and self.allow_sharing:
            raise StructuralNavigationError("strict_tree requer allow_sharing=False")
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def field_map(self) -> dict[str, StructuralField]:
        return {field.name: field for field in self.fields}

    def fields_by_role(self, role: str) -> tuple[StructuralField, ...]:
        return tuple(field for field in self.fields if field.semantic_role == role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "fields": [field.to_dict() for field in self.fields],
            "allow_cycles": self.allow_cycles,
            "allow_sharing": self.allow_sharing,
            "strict_tree": self.strict_tree,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StructuralReference:
    target: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target}


@dataclass(frozen=True)
class StructuralValue:
    value: int
    bit_width: int

    def __post_init__(self) -> None:
        if int(self.value) < 0:
            raise StructuralNavigationError("StructuralValue.value deve ser nao negativo")
        if int(self.bit_width) <= 0:
            raise StructuralNavigationError("StructuralValue.bit_width deve ser positivo")
        if int(self.value) >= 2 ** int(self.bit_width):
            raise StructuralNavigationError("StructuralValue.value fora do dominio")
        object.__setattr__(self, "value", int(self.value))
        object.__setattr__(self, "bit_width", int(self.bit_width))

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "bit_width": self.bit_width}


@dataclass(frozen=True)
class StructuralNode:
    local_node_id: str
    type_id: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.local_node_id:
            raise StructuralNavigationError("StructuralNode.local_node_id nao pode ser vazio")
        if not self.type_id:
            raise StructuralNavigationError("StructuralNode.type_id nao pode ser vazio")
        object.__setattr__(self, "fields", _freeze_mapping(self.fields))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_node_id": self.local_node_id,
            "type_id": self.type_id,
            "fields": _json_safe(dict(self.fields)),
            "provenance": _json_safe(dict(self.provenance)),
        }


@dataclass(frozen=True)
class StructuralHeap:
    types: tuple[StructuralType, ...]
    nodes: tuple[StructuralNode, ...]
    roots: tuple[str, ...]
    allow_cycles: bool = True
    allow_sharing: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        types = tuple(self.types)
        nodes = tuple(self.nodes)
        roots = tuple(str(root) for root in self.roots)
        if not types:
            raise StructuralNavigationError("StructuralHeap requer ao menos um tipo")
        if not nodes and roots:
            raise StructuralNavigationError("StructuralHeap sem nos nao pode ter roots")
        if len({item.type_id for item in types}) != len(types):
            raise StructuralNavigationError("StructuralHeap possui type_id duplicado")
        if len({item.local_node_id for item in nodes}) != len(nodes):
            raise StructuralNavigationError("StructuralHeap possui local_node_id duplicado")
        object.__setattr__(self, "types", types)
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def type_map(self) -> dict[str, StructuralType]:
        return {item.type_id: item for item in self.types}

    def node_map(self) -> dict[str, StructuralNode]:
        return {item.local_node_id: item for item in self.nodes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "navigation_version": "v2",
            "types": [item.to_dict() for item in self.types],
            "nodes": [item.to_dict() for item in self.nodes],
            "roots": list(self.roots),
            "allow_cycles": self.allow_cycles,
            "allow_sharing": self.allow_sharing,
            "metadata": _json_safe(dict(self.metadata)),
        }


@dataclass(frozen=True)
class StructuralPointer:
    equivalence_fingerprint: str | None = None
    canonical_node_id: str | None = None
    expected_type: str | None = None
    nullable: bool = True
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "equivalence_fingerprint": self.equivalence_fingerprint,
            "canonical_node_id": self.canonical_node_id,
            "expected_type": self.expected_type,
            "nullable": self.nullable,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class StructuralSelector:
    selector_id: str
    kind: str
    field_name: str | None = None
    index: int | None = None
    expected_value: Any = None
    absence_policy: AbsencePolicy = "return_null"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.absence_policy not in VALID_ABSENCE_POLICIES:
            raise StructuralNavigationError(f"absence_policy invalida: {self.absence_policy}")
        if self.index is not None and int(self.index) < 0:
            raise StructuralNavigationError("StructuralSelector.index deve ser nao negativo")
        object.__setattr__(self, "index", None if self.index is None else int(self.index))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    @staticmethod
    def value(field_name: str, *, expected_value: Any = None) -> "StructuralSelector":
        return StructuralSelector(f"value:{field_name}", "value", field_name=field_name, expected_value=expected_value)

    @staticmethod
    def reference(field_name: str) -> "StructuralSelector":
        return StructuralSelector(f"reference:{field_name}", "reference", field_name=field_name)

    @staticmethod
    def role(role: str, *, index: int | None = None, field_name: str | None = None) -> "StructuralSelector":
        suffix = "" if index is None else f":{index}"
        return StructuralSelector(f"{role}:{field_name or '*'}{suffix}", role, field_name=field_name, index=index)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector_id": self.selector_id,
            "kind": self.kind,
            "field_name": self.field_name,
            "index": self.index,
            "expected_value": self.expected_value,
            "absence_policy": self.absence_policy,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class RhoDResult:
    input_canonical_pointer: str | None
    selector: StructuralSelector
    resolved_canonical_pointer: str | None = None
    value_location: tuple[str, str] | None = None
    value: int | None = None
    status: str = "resolved"
    null_state: str = "not_null"
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_canonical_pointer": self.input_canonical_pointer,
            "selector": self.selector.to_dict(),
            "resolved_canonical_pointer": self.resolved_canonical_pointer,
            "value_location": list(self.value_location) if self.value_location else None,
            "value": self.value,
            "status": self.status,
            "null_state": self.null_state,
            "diagnostics": list(self.diagnostics),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class StructuralEquivalenceClass:
    canonical_heap: StructuralHeap | None
    equivalence_fingerprint: str | None
    local_to_canonical: Mapping[str, str]
    canonical_to_local: Mapping[str, str]
    canonical_order: tuple[str, ...]
    status: str = "canonical"
    candidate_count: int = 0
    candidate_limit: int = 0
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "local_to_canonical", MappingProxyType(dict(self.local_to_canonical)))
        object.__setattr__(self, "canonical_to_local", MappingProxyType(dict(self.canonical_to_local)))
        object.__setattr__(self, "canonical_order", tuple(self.canonical_order))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_heap": None if self.canonical_heap is None else self.canonical_heap.to_dict(),
            "equivalence_fingerprint": self.equivalence_fingerprint,
            "local_to_canonical": dict(self.local_to_canonical),
            "canonical_to_local": dict(self.canonical_to_local),
            "canonical_order": list(self.canonical_order),
            "status": self.status,
            "candidate_count": self.candidate_count,
            "candidate_limit": self.candidate_limit,
            "diagnostics": list(self.diagnostics),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class StructuralOperation:
    operation_id: str
    operation: str
    selector: StructuralSelector | None = None
    predicate: str | None = None
    exactness: str = "exact"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation": self.operation,
            "selector": None if self.selector is None else self.selector.to_dict(),
            "predicate": self.predicate,
            "exactness": self.exactness,
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class StructuralNavigationPlan:
    navigation_version: str
    equivalence_class: StructuralEquivalenceClass
    operation: StructuralOperation
    node_count: int
    pointer_domain: tuple[str, ...]
    selector_domain: tuple[str, ...]
    value_width: int
    pointer_width: int
    output_width: int
    register_layout: Mapping[str, Any]
    null_encoding: int
    rho_table: Mapping[int, RhoDResult]
    memory_values: tuple[int, ...]
    exactness: str
    lowering_strategy: str
    resource_estimates: Mapping[str, Any]
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pointer_domain", tuple(self.pointer_domain))
        object.__setattr__(self, "selector_domain", tuple(self.selector_domain))
        object.__setattr__(self, "register_layout", _freeze_mapping(self.register_layout))
        object.__setattr__(self, "rho_table", MappingProxyType(dict(self.rho_table)))
        object.__setattr__(self, "memory_values", tuple(int(value) for value in self.memory_values))
        object.__setattr__(self, "resource_estimates", _freeze_mapping(self.resource_estimates))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "navigation_version": self.navigation_version,
            "equivalence_fingerprint": self.equivalence_class.equivalence_fingerprint,
            "operation": self.operation.to_dict(),
            "node_count": self.node_count,
            "pointer_domain": list(self.pointer_domain),
            "selector_domain": list(self.selector_domain),
            "value_width": self.value_width,
            "pointer_width": self.pointer_width,
            "output_width": self.output_width,
            "register_layout": _json_safe(dict(self.register_layout)),
            "null_encoding": self.null_encoding,
            "rho_table": {str(key): value.to_dict() for key, value in self.rho_table.items()},
            "memory_values": list(self.memory_values),
            "exactness": self.exactness,
            "lowering_strategy": self.lowering_strategy,
            "resource_estimates": _json_safe(dict(self.resource_estimates)),
            "diagnostics": list(self.diagnostics),
            "provenance": _json_safe(dict(self.provenance)),
        }


@dataclass(frozen=True)
class SemanticVerification:
    status: str
    finite_domain_semantic_verification: bool
    checks: Mapping[str, Any]
    diagnostics: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", _freeze_mapping(self.checks))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "finite_domain_semantic_verification": self.finite_domain_semantic_verification,
            "checks": _json_safe(dict(self.checks)),
            "diagnostics": list(self.diagnostics),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class StructuralNavigationResult:
    circuit: Any
    navigation_name: str
    circuit_format: str
    metadata: Mapping[str, Any]
    source: StructuralHeap
    validated_structure: StructuralHeap
    canonical_structure: StructuralHeap | None
    equivalence_class: StructuralEquivalenceClass
    plan: StructuralNavigationPlan
    operation: StructuralOperation
    verification: SemanticVerification

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def navigation_version(self) -> str:
        return "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "navigation_version": "v2",
            "navigation_name": self.navigation_name,
            "circuit_format": self.circuit_format,
            "metadata": _json_safe(dict(self.metadata)),
            "source": self.source.to_dict(),
            "validated_structure": self.validated_structure.to_dict(),
            "canonical_structure": None if self.canonical_structure is None else self.canonical_structure.to_dict(),
            "equivalence_class": self.equivalence_class.to_dict(),
            "plan": self.plan.to_dict(),
            "operation": self.operation.to_dict(),
            "verification": self.verification.to_dict(),
        }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    return {"type": type(value).__name__, "module": type(value).__module__}

