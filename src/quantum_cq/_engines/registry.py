"""Lazy registry for engine adapters."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from quantum_cq._engines.errors import UnknownEngineError
from quantum_cq._engines.protocols import EngineAdapterProtocol


_ENGINE_SPECS: dict[str, tuple[str, str]] = {
    "qiskit": ("quantum_cq._engines.qiskit", "QiskitEngineAdapter"),
    "pennylane": ("quantum_cq._engines.pennylane", "PennyLaneEngineAdapter"),
    "cirq": ("quantum_cq._engines.cirq", "CirqEngineAdapter"),
    "braket": ("quantum_cq._engines.braket", "BraketEngineAdapter"),
    "cudaq": ("quantum_cq._engines.cudaq", "CudaQEngineAdapter"),
}


def engine_names() -> list[str]:
    return list(_ENGINE_SPECS)


def get_engine_adapter(engine: str) -> EngineAdapterProtocol:
    normalized = engine.lower()
    if normalized not in _ENGINE_SPECS:
        raise UnknownEngineError(f"Engine desconhecida: {engine}")

    module_name, class_name = _ENGINE_SPECS[normalized]
    module = import_module(module_name)
    adapter_cls = getattr(module, class_name)
    return adapter_cls()


def engine_catalog() -> list[dict[str, Any]]:
    catalog = []
    for name in engine_names():
        adapter = get_engine_adapter(name)
        capabilities = adapter.capabilities()
        catalog.append(
            {
                "engine": name,
                "installed": capabilities.installed,
                "default": name == "qiskit",
                "status": "supported" if name == "qiskit" else "optional",
            }
        )
    return catalog


def engine_capabilities(engine: str) -> dict[str, Any]:
    return get_engine_adapter(engine).capabilities().to_dict()
