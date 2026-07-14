"""SDK-free compatibility contracts shared by core services and engines."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol


CompatibilityStatus = Literal[
    "compatible",
    "compatible_after_lowering",
    "incompatible",
    "not_tested",
]


class CapabilityModel(Protocol):
    engine: str

    def status(self, feature: str) -> str:
        """Return the declared capability status for a feature."""


@dataclass(frozen=True)
class ComponentRequirement:
    feature: str
    alternatives: tuple[str, ...] = ()
    allow_lowered: bool = True
    description: str = ""
    category: str = "operation"

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature", str(self.feature))
        object.__setattr__(self, "alternatives", tuple(str(item) for item in self.alternatives))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "description", str(self.description))

    @property
    def candidates(self) -> tuple[str, ...]:
        return (self.feature, *self.alternatives)


@dataclass(frozen=True)
class CompatibilityReport:
    component: str
    engine: str
    requirements: tuple[ComponentRequirement, ...]
    capabilities_considered: Mapping[str, str]
    satisfied: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    alternatives_used: Mapping[str, str] = field(default_factory=dict)
    lowerings: tuple[str, ...] = ()
    status: CompatibilityStatus = "compatible"
    reason: str = ""
    circuit_requirements: Any = None
    target: Any = None
    hardware: Mapping[str, Any] = field(default_factory=dict)
    unknowns: tuple[str, ...] = ()
    placement_required: bool = False
    routing_required: bool = False
    scheduling_required: bool = False
    placement_status: str = "not_analyzed"
    routing_status: str = "not_analyzed"
    scheduling_status: str = "not_analyzed"
    physical_execution_claimed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", tuple(self.requirements))
        object.__setattr__(
            self,
            "capabilities_considered",
            MappingProxyType(dict(self.capabilities_considered)),
        )
        object.__setattr__(self, "satisfied", tuple(self.satisfied))
        object.__setattr__(self, "missing", tuple(self.missing))
        object.__setattr__(self, "alternatives_used", MappingProxyType(dict(self.alternatives_used)))
        object.__setattr__(self, "lowerings", tuple(self.lowerings))
        object.__setattr__(self, "hardware", MappingProxyType(dict(self.hardware)))
        object.__setattr__(self, "unknowns", tuple(self.unknowns))

    @property
    def compatible(self) -> bool:
        return self.status in {"compatible", "compatible_after_lowering"}


class CompatibilityEvaluator:
    """Evaluate component requirements against declared capabilities only."""

    def evaluate(
        self,
        *,
        component: str,
        capabilities: CapabilityModel,
        requirements: tuple[ComponentRequirement, ...],
        circuit_requirements: Any = None,
        target: Any = None,
        hardware: Mapping[str, Any] | None = None,
    ) -> CompatibilityReport:
        satisfied: list[str] = []
        missing: list[str] = []
        not_tested: list[str] = []
        lowerings: list[str] = []
        alternatives_used: dict[str, str] = {}
        considered: dict[str, str] = {}

        for requirement in requirements:
            matched_feature: str | None = None
            matched_status: str | None = None
            best_rank = len(_STATUS_PRIORITY)
            for feature in requirement.candidates:
                status = capabilities.status(feature)
                considered[feature] = status
                if status == "lowered" and not requirement.allow_lowered:
                    status = "unsupported"
                rank = _STATUS_PRIORITY.get(status, len(_STATUS_PRIORITY))
                if rank < best_rank:
                    matched_feature = feature
                    matched_status = status
                    best_rank = rank
                if status == "supported":
                    break

            if matched_status == "supported":
                satisfied.append(requirement.feature)
                if matched_feature != requirement.feature:
                    alternatives_used[requirement.feature] = str(matched_feature)
            elif matched_status == "lowered":
                satisfied.append(requirement.feature)
                lowerings.append(requirement.feature)
                if matched_feature != requirement.feature:
                    alternatives_used[requirement.feature] = str(matched_feature)
            elif matched_status in {"not_tested", "experimental"}:
                not_tested.append(requirement.feature)
            else:
                missing.append(requirement.feature)

        if missing:
            status: CompatibilityStatus = "incompatible"
            reason = "requirements missing: " + ", ".join(missing)
        elif not_tested:
            status = "not_tested"
            reason = "requirements not tested: " + ", ".join(not_tested)
        elif lowerings:
            status = "compatible_after_lowering"
            reason = "compatible after lowering: " + ", ".join(lowerings)
        else:
            status = "compatible"
            reason = "all requirements supported"

        hardware_data = dict(hardware or {})
        return CompatibilityReport(
            component=component,
            engine=capabilities.engine,
            requirements=requirements,
            capabilities_considered=considered,
            satisfied=tuple(satisfied),
            missing=tuple(missing),
            alternatives_used=alternatives_used,
            lowerings=tuple(lowerings),
            status=status,
            reason=reason,
            circuit_requirements=circuit_requirements,
            target=target,
            hardware=hardware_data,
            unknowns=tuple(hardware_data.get("unknowns", ())),
            placement_required=hardware_data.get("placement_status") == "required",
            routing_required=hardware_data.get("routing_status") == "required",
            scheduling_required=hardware_data.get("scheduling_status") == "required",
            placement_status=str(hardware_data.get("placement_status", "not_analyzed")),
            routing_status=str(hardware_data.get("routing_status", "not_analyzed")),
            scheduling_status=str(hardware_data.get("scheduling_status", "not_analyzed")),
            physical_execution_claimed=False,
        )


def normalize_requirement(value: Any) -> ComponentRequirement:
    if isinstance(value, ComponentRequirement):
        return value
    if isinstance(value, str):
        return ComponentRequirement(value)
    if isinstance(value, Mapping):
        return ComponentRequirement(
            feature=str(value["feature"]),
            alternatives=tuple(str(item) for item in value.get("alternatives", ())),
            allow_lowered=bool(value.get("allow_lowered", True)),
            description=str(value.get("description", "")),
            category=str(value.get("category", "operation")),
        )
    raise TypeError(f"Requisito de componente invalido: {value!r}")


_STATUS_PRIORITY = {
    "supported": 0,
    "lowered": 1,
    "experimental": 2,
    "not_tested": 3,
    "unsupported": 4,
}
