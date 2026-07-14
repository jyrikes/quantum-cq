"""Specification-style compatibility evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from quantum_cq._engines.capabilities import EngineCapabilities


CompatibilityStatus = Literal[
    "compatible",
    "compatible_after_lowering",
    "incompatible",
    "not_tested",
]


@dataclass(frozen=True)
class ComponentRequirement:
    feature: str
    alternatives: tuple[str, ...] = ()
    allow_lowered: bool = True
    description: str = ""
    category: str = "operation"

    def __post_init__(self) -> None:
        object.__setattr__(self, "alternatives", tuple(self.alternatives))

    @property
    def candidates(self) -> tuple[str, ...]:
        return (self.feature, *self.alternatives)


@dataclass(frozen=True)
class CompatibilityReport:
    component: str
    engine: str
    requirements: tuple[ComponentRequirement, ...]
    capabilities_considered: dict[str, str]
    satisfied: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    alternatives_used: dict[str, str] = field(default_factory=dict)
    lowerings: tuple[str, ...] = ()
    status: CompatibilityStatus = "compatible"
    reason: str = ""
    circuit_requirements: Any = None
    target: Any = None
    hardware: dict[str, Any] = field(default_factory=dict)
    unknowns: tuple[str, ...] = ()
    placement_required: bool = False
    routing_required: bool = False
    scheduling_required: bool = False
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
        capabilities: EngineCapabilities,
        requirements: tuple[ComponentRequirement, ...],
        circuit_requirements: Any = None,
        target: Any = None,
        hardware: dict[str, Any] | None = None,
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
            hardware=hardware or {},
            unknowns=tuple((hardware or {}).get("unknowns", ())),
            placement_required=bool((hardware or {}).get("placement_required", False)),
            routing_required=bool((hardware or {}).get("routing_required", False)),
            scheduling_required=bool((hardware or {}).get("scheduling_required", False)),
            physical_execution_claimed=False,
        )


_STATUS_PRIORITY = {
    "supported": 0,
    "lowered": 1,
    "experimental": 2,
    "not_tested": 3,
    "unsupported": 4,
}
