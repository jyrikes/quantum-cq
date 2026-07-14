"""Engine bundle composed from coherent ports."""

from __future__ import annotations

from dataclasses import dataclass

from quantum_cq._engines.protocols import (
    AvailabilityPort,
    CapabilitiesPort,
    CompilerPort,
    EmitterPort,
    ExecutorPort,
    ResultDecoderPort,
    TranspilerPort,
)


@dataclass(frozen=True)
class EngineBundle:
    engine_id: str
    availability: AvailabilityPort
    capabilities: CapabilitiesPort
    emitter: EmitterPort
    compiler: CompilerPort
    executor: ExecutorPort
    decoder: ResultDecoderPort
    transpiler: TranspilerPort | None = None

    def __post_init__(self) -> None:
        ports = (
            self.availability,
            self.capabilities,
            self.emitter,
            self.compiler,
            self.executor,
            self.decoder,
            *((self.transpiler,) if self.transpiler is not None else ()),
        )
        mismatched = [
            getattr(port, "engine_id", None)
            for port in ports
            if getattr(port, "engine_id", None) != self.engine_id
        ]
        if mismatched:
            raise ValueError(
                f"EngineBundle '{self.engine_id}' recebeu ports de engines diferentes: {mismatched}"
            )
