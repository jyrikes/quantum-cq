"""Lazy registry for engine bundles."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from quantum_cq._engines.bundle import EngineBundle
from quantum_cq._engines.errors import UnknownEngineError


_ENGINE_SPECS: dict[str, tuple[str, str]] = {
    "qiskit": ("quantum_cq._engines.qiskit", "create_bundle"),
    "pennylane": ("quantum_cq._engines.pennylane", "create_bundle"),
    "cirq": ("quantum_cq._engines.cirq", "create_bundle"),
    "braket": ("quantum_cq._engines.braket", "create_bundle"),
    "cudaq": ("quantum_cq._engines.cudaq", "create_bundle"),
}


def engine_names() -> list[str]:
    return list(_ENGINE_SPECS)


def get_engine_bundle(engine: str) -> EngineBundle:
    normalized = engine.lower()
    if normalized not in _ENGINE_SPECS:
        raise UnknownEngineError(f"Engine desconhecida: {engine}")

    module_name, factory_name = _ENGINE_SPECS[normalized]
    module = import_module(module_name)
    factory = getattr(module, factory_name)
    return factory()


def get_engine_adapter(engine: str) -> Any:
    """Compatibility wrapper for the Run 1 internal helper name."""

    module_name, _ = _ENGINE_SPECS[engine.lower()]
    module = import_module(module_name)
    adapter_cls = getattr(module, f"{engine.capitalize()}EngineAdapter", None)
    if adapter_cls is not None:
        return adapter_cls()
    return get_engine_bundle(engine)


def engine_catalog() -> list[dict[str, Any]]:
    from quantum_cq._engines.service import default_engine_service

    return default_engine_service().engines()


def engine_capabilities(engine: str) -> dict[str, Any]:
    from quantum_cq._engines.service import default_engine_service

    return default_engine_service().capabilities(engine)
