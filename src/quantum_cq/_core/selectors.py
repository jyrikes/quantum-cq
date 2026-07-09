"""Selecao automatica de encodings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from quantum_cq._core.data import QuantumData
from quantum_cq._core.interfaces import EncodingProtocol


class _EncoderRegistryLike(Protocol):
    def all(self) -> Iterable[EncodingProtocol]: ...


def _encoder_list(source: Iterable[EncodingProtocol] | Any) -> list[EncodingProtocol]:
    if hasattr(source, "all"):
        return list(cast(_EncoderRegistryLike, source).all())
    return list(cast(Iterable[EncodingProtocol], source))


@dataclass
class EncodingSelectionContext:
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    algorithm_name: str | None = None
    role: str | None = None


def _metadata(data: Any, context: EncodingSelectionContext | None = None) -> dict[str, Any]:
    metadata = dict(context.metadata) if context is not None else {}
    if isinstance(data, QuantumData):
        metadata.update(data.metadata)

    return metadata


class EncodingSelector:
    def __init__(
        self,
        encoders: Iterable[EncodingProtocol] | Any,
        navigation_encoders: Iterable[EncodingProtocol] | Any | None = None,
    ):
        self.encoders = _encoder_list(encoders)
        self.navigation_encoders = (
            None
            if navigation_encoders is None
            else _encoder_list(navigation_encoders)
        )

    def select(
        self,
        data: Any,
        context: EncodingSelectionContext | None = None,
    ) -> EncodingProtocol:
        role = (context.role if context is not None else None) or "state"
        if role == "input":
            role = "state"
        if role not in {"state", "oracle", "operator", "navigation"}:
            raise ValueError(f"Role de encoding invalido: {role}")
        if role == "navigation":
            return self._select_navigation(data)
        if role != "state":
            raise NotImplementedError(f"Selecao contextual para role='{role}' ainda nao implementada")

        hint = _metadata(data, context).get("encoding_hint")
        if hint is not None:
            return self._select_hint(str(hint).lower(), data)

        for candidate in self._auto_candidates(data):
            return candidate

        raise ValueError("Nenhum encoding disponivel para os dados informados")

    def choose(
        self,
        data: Any,
        context: EncodingSelectionContext | None = None,
    ) -> EncodingProtocol:
        return self.select(data, context=context)

    def rank_candidates(self, data: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": encoder.name,
                "family": getattr(encoder, "family", ""),
                "auto_selectable": getattr(encoder, "auto_selectable", False),
            }
            for encoder in self._auto_candidates(data)
        ]

    def explain(self, data: Any) -> list[dict[str, Any]]:
        return self.rank_candidates(data)

    def _select_hint(self, hint: str, data: Any) -> EncodingProtocol:
        for encoder in self.encoders:
            if getattr(encoder, "name", "").lower() == hint:
                if not encoder.can_handle(data):
                    raise ValueError(f"Encoding '{hint}' nao pode lidar com os dados informados")

                return encoder

        raise ValueError(f"Encoding '{hint}' nao registrado")

    def _auto_candidates(self, data: Any) -> list[EncodingProtocol]:
        return [
            encoder
            for encoder in self.encoders
            if getattr(encoder, "auto_selectable", False) and encoder.can_handle(data)
        ]

    def _select_navigation(self, data: Any) -> EncodingProtocol:
        from quantum_cq._core.handlers import default_navigation_registry
        from quantum_cq._navigation.memory import AddressedMemory, GraphData

        value = getattr(data, "value", data)
        if self.navigation_encoders is None:
            self.navigation_encoders = default_navigation_registry().all()

        expected_name: str | None = None
        if isinstance(value, AddressedMemory):
            expected_name = "addressed_memory"
        elif isinstance(value, GraphData):
            expected_name = "graph_navigation"
        else:
            raise ValueError("Nenhum encoding de navigation disponivel para os dados informados")

        for encoder in self.navigation_encoders:
            if getattr(encoder, "name", "") == expected_name and encoder.can_handle(value):
                return encoder

        raise ValueError(f"Encoding de navigation '{expected_name}' nao registrado")
