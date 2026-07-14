"""Component descriptors and read-only public catalog service."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Mapping

from quantum_cq._engines.compatibility import (
    CompatibilityEvaluator,
    CompatibilityReport,
    ComponentRequirement,
)
from quantum_cq._engines.capabilities import EngineCapabilities


@dataclass(frozen=True)
class ComponentDescriptor:
    name: str
    category: str
    family: str = ""
    status: str = "implemented"
    description: str = ""
    role: str = ""
    access_path: str = ""
    requirements: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    category: str
    family: str = ""
    status: str = "implemented"
    description: str = ""
    role: str = ""
    access_path: str = ""
    requirements: tuple[ComponentRequirement, ...] = ()
    compatibility: CompatibilityReport | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ComponentService:
    """Read-only service over existing component registries."""

    def __init__(
        self,
        *,
        encoding_registry: Any = None,
        oracle_registry: Any = None,
        primitive_registry: Any = None,
        operator_registry: Any = None,
        algorithm_registry: Any = None,
        navigation_registry: Any = None,
        evaluator: CompatibilityEvaluator | None = None,
        capability_resolver: Callable[[str], EngineCapabilities] | None = None,
    ) -> None:
        from quantum_cq._core.handlers import (
            default_algorithm_registry,
            default_encoding_registry,
            default_navigation_registry,
            default_operator_registry,
            default_oracle_registry,
            default_primitive_registry,
        )

        self._registries = {
            "encoding": encoding_registry or default_encoding_registry(),
            "oracle": oracle_registry or default_oracle_registry(),
            "primitive": primitive_registry or default_primitive_registry(),
            "operator": operator_registry or default_operator_registry(),
            "algorithm": algorithm_registry or default_algorithm_registry(),
            "navigation": navigation_registry or default_navigation_registry(),
        }
        self._evaluator = evaluator or CompatibilityEvaluator()
        self._capability_resolver = capability_resolver

    def resolve(self, category: str, name: str, *args: Any, **kwargs: Any) -> Any:
        registry = self._registries[category]
        if hasattr(registry, "create"):
            return registry.create(name, *args, **kwargs)
        if args or kwargs:
            raise TypeError(f"Registry '{category}' nao aceita argumentos de construcao")
        return registry.get(name)

    def catalog(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        name: str | None = None,
        engine: str | None = None,
    ) -> tuple[CatalogEntry, ...]:
        entries = [
            self._entry(descriptor, engine=engine)
            for descriptor in self._descriptors()
            if _matches(descriptor, category=category, status=status, name=name)
        ]
        if engine is not None:
            entries = [
                entry
                for entry in entries
                if entry.compatibility is not None
                and entry.compatibility.status in {"compatible", "compatible_after_lowering"}
            ]
        return tuple(entries)

    def requirements(self, category: str, name: str) -> tuple[ComponentRequirement, ...]:
        for descriptor in self._descriptors():
            if descriptor.category == category and descriptor.name == name:
                return _requirements(descriptor)
        raise KeyError(f"Componente '{category}:{name}' nao encontrado")

    def _descriptors(self) -> tuple[ComponentDescriptor, ...]:
        descriptors: list[ComponentDescriptor] = []
        for category, registry in self._registries.items():
            if hasattr(registry, "descriptors"):
                descriptors.extend(registry.descriptors())
                continue
            descriptors.extend(
                ComponentDescriptor(name=item, category=category)
                for item in registry.names()
            )
        return tuple(descriptors)

    def _entry(self, descriptor: ComponentDescriptor, *, engine: str | None) -> CatalogEntry:
        requirements = _requirements(descriptor)
        compatibility = self._compatibility(descriptor, requirements, engine) if engine else None
        return CatalogEntry(
            name=descriptor.name,
            category=descriptor.category,
            family=descriptor.family,
            status=descriptor.status,
            description=descriptor.description,
            role=descriptor.role,
            access_path=descriptor.access_path,
            requirements=requirements,
            compatibility=compatibility,
            metadata=descriptor.metadata,
        )

    def _compatibility(
        self,
        descriptor: ComponentDescriptor,
        requirements: tuple[ComponentRequirement, ...],
        engine: str | None,
    ) -> CompatibilityReport:
        if self._capability_resolver is None:
            raise ValueError("ComponentService requer capability_resolver para avaliar engine")
        capabilities = self._capability_resolver(str(engine))
        return self._evaluator.evaluate(
            component=f"{descriptor.category}:{descriptor.name}",
            capabilities=capabilities,
            requirements=requirements,
        )


def _requirements(descriptor: ComponentDescriptor) -> tuple[ComponentRequirement, ...]:
    return tuple(ComponentRequirement(feature) for feature in descriptor.requirements)


def _matches(
    descriptor: ComponentDescriptor,
    *,
    category: str | None,
    status: str | None,
    name: str | None,
) -> bool:
    if category is not None and descriptor.category != category:
        return False
    if status is not None and descriptor.status != status:
        return False
    if name is not None and descriptor.name != name:
        return False
    return True
