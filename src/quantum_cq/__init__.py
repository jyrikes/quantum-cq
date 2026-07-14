"""quantum_cq package."""

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from quantum_cq._core.facade import CQ
from quantum_cq._core.data import QuantumData
from quantum_cq._core.interfaces import (
    AlgorithmBuilderProtocol,
    AlgorithmHandler,
    AlgorithmProtocol,
    ArithmeticOracleProtocol,
    BackendAdapter,
    BackendAdapterProtocol,
    BlockEncodingProtocol,
    CircuitBuilderProtocol,
    CircuitExporterProtocol,
    CircuitFactoryProtocol,
    CircuitLikeProtocol,
    CompilerAdapterProtocol,
    ControlledUnitaryProtocol,
    DiffuserProtocol,
    EncodingHandler,
    EncodingProtocol,
    EncodingSelectorProtocol,
    FourierTransformProtocol,
    GraphNavigationProtocol,
    HamiltonianEncodingProtocol,
    LinearSystemProblemProtocol,
    NavigationEncodingProtocol,
    MetricsCollectorProtocol,
    OperatorProtocol,
    OperatorEncodingProtocol,
    OracleProtocol,
    OracleEncodingProtocol,
    PhaseOracleProtocol,
    PipelineBuilderProtocol,
    PowerableUnitaryProtocol,
    PrimitiveProtocol,
    PredicateOracleProtocol,
    RegistryProtocol,
    ResultHandler,
    StateEncodingProtocol,
    StatePreparationProtocol,
    UnitaryProtocol,
    AddressedEncodingProtocol,
)
from quantum_cq._core.logging_config import configure_logging
from quantum_cq._navigation.memory import (
    AddressedMemory,
    AddressedMemoryEncoding,
    GraphData,
    GraphNavigationEncoding,
)
from quantum_cq._core.results import (
    AlgorithmCircuit,
    AlgorithmSpec,
    CompilerResult,
    EncodedCircuit,
    NavigationCircuit,
    OperatorCircuit,
    OracleCircuit,
    QuantumResult,
)
from quantum_cq._core.components import CatalogEntry
from quantum_cq._core.circuits import CircuitDescriptor, CircuitRequirements
from quantum_cq._engines.compatibility import CompatibilityReport, ComponentRequirement
from quantum_cq._engines.measurement import MeasurementContract
from quantum_cq._engines.results import CompiledArtifact, EngineResult, NativeTranspilationResult
from quantum_cq._circuits.unitary import CustomUnitary
from quantum_cq._hardware.models import (
    ExecutionContext,
    ExecutionTarget,
    ExecutionTargetDescriptor,
    NativeInstruction,
    TargetArchitecture,
    TargetDatum,
    TargetProvenance,
    TargetStateSnapshot,
    TopologyEdge,
)
from quantum_cq._core.settings import (
    PipelineSettings,
    RuntimeSettings,
    get_pipeline_settings,
    get_runtime_settings,
)
from quantum_cq._runtime.runtime import IBMRuntimeConfig

try:
    __version__ = version("quantum-cq")
except PackageNotFoundError:
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from quantum_cq._runtime.experiment import (
        ExperimentPlan,
        ExperimentResult,
        ExperimentSpec,
        PipelineResult,
    )
    from quantum_cq._runtime.pipeline import BenchmarkingPipeline


_LAZY_EXPORTS = {
    "ExperimentPlan": ("quantum_cq._runtime.experiment", "ExperimentPlan"),
    "ExperimentSpec": ("quantum_cq._runtime.experiment", "ExperimentSpec"),
    "ExperimentResult": ("quantum_cq._runtime.experiment", "ExperimentResult"),
    "PipelineResult": ("quantum_cq._runtime.experiment", "PipelineResult"),
    "BenchmarkingPipeline": ("quantum_cq._runtime.pipeline", "BenchmarkingPipeline"),
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        module_name, attr_name = _LAZY_EXPORTS[name]
        value = getattr(import_module(module_name), attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module 'quantum_cq' has no attribute {name!r}")

__all__ = [
    "__version__",
    "CQ",
    "QuantumData",
    "QuantumResult",
    "EncodedCircuit",
    "AlgorithmCircuit",
    "AlgorithmSpec",
    "CompilerResult",
    "CompiledArtifact",
    "CatalogEntry",
    "CircuitDescriptor",
    "CircuitRequirements",
    "CompatibilityReport",
    "ComponentRequirement",
    "CustomUnitary",
    "EngineResult",
    "ExecutionContext",
    "ExecutionTarget",
    "ExecutionTargetDescriptor",
    "MeasurementContract",
    "NativeInstruction",
    "NativeTranspilationResult",
    "TargetArchitecture",
    "TargetDatum",
    "TargetProvenance",
    "TargetStateSnapshot",
    "TopologyEdge",
    "OperatorCircuit",
    "OracleCircuit",
    "NavigationCircuit",
    "AddressedMemory",
    "AddressedMemoryEncoding",
    "GraphData",
    "GraphNavigationEncoding",
    "ExperimentPlan",
    "ExperimentSpec",
    "ExperimentResult",
    "PipelineResult",
    "BenchmarkingPipeline",
    "IBMRuntimeConfig",
    "EncodingHandler",
    "EncodingProtocol",
    "StateEncodingProtocol",
    "OracleEncodingProtocol",
    "OperatorEncodingProtocol",
    "NavigationEncodingProtocol",
    "AddressedEncodingProtocol",
    "GraphNavigationProtocol",
    "AlgorithmBuilderProtocol",
    "AlgorithmHandler",
    "AlgorithmProtocol",
    "ArithmeticOracleProtocol",
    "BackendAdapter",
    "BackendAdapterProtocol",
    "BlockEncodingProtocol",
    "CircuitBuilderProtocol",
    "CircuitExporterProtocol",
    "CircuitFactoryProtocol",
    "CircuitLikeProtocol",
    "CompilerAdapterProtocol",
    "ControlledUnitaryProtocol",
    "DiffuserProtocol",
    "EncodingSelectorProtocol",
    "FourierTransformProtocol",
    "HamiltonianEncodingProtocol",
    "LinearSystemProblemProtocol",
    "RegistryProtocol",
    "PipelineBuilderProtocol",
    "MetricsCollectorProtocol",
    "OperatorProtocol",
    "PrimitiveProtocol",
    "OracleProtocol",
    "PhaseOracleProtocol",
    "PowerableUnitaryProtocol",
    "PredicateOracleProtocol",
    "ResultHandler",
    "StatePreparationProtocol",
    "UnitaryProtocol",
    "configure_logging",
    "PipelineSettings",
    "RuntimeSettings",
    "get_pipeline_settings",
    "get_runtime_settings",
]
