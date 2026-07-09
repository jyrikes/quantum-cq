from pathlib import Path
import logging
import ast
from typing import Any

import pytest


class FakeJob:
    def result(self) -> Any:
        return None

    def job_id(self) -> str:
        return "fake-job"

    def status(self) -> str:
        return "DONE"

    def cancel(self) -> None:
        return None


class FakeSampler:
    def run(self, pubs: Any, *, shots: int | None = None) -> FakeJob:
        return FakeJob()

def test_python_interpreter():
    import sys
    print(sys.executable)
    print(sys.version)
    assert True

def test_source_modules_exist():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "quantum_cq"

    assert (package / "runtime.py").exists()
    assert (package / "pipeline.py").exists()
    assert (package / "compact.py").exists()
    assert (package / "algorithms.py").exists()
    assert (package / "oracles.py").exists()
    assert (package / "primitives.py").exists()
    assert (package / "navigation.py").exists()
    assert (package / "walks.py").exists()
    assert (package / "adapters.py").exists()
    assert (package / "settings.py").exists()

    for private_package in (
        "_core",
        "_circuits",
        "_encodings",
        "_navigation",
        "_algorithms",
        "_runtime",
        "_tools",
    ):
        assert (package / private_package / "__init__.py").exists()


def test_package_imports_without_running_runtime_cells():
    import quantum_cq

    assert hasattr(quantum_cq, "CQ")
    assert hasattr(quantum_cq, "QuantumData")


def test_compact_module_exports_core_objects():
    from quantum_cq.compact import QC, CircuitIR, CompactAdapter, QiskitExporter

    assert QC is not None
    assert CircuitIR is not None
    assert CompactAdapter is not None
    assert QiskitExporter is not None


def test_adapters_reexport_compact_adapter_and_exporter():
    from quantum_cq.adapters import CompactAdapter, QiskitExporter

    assert CompactAdapter.__name__ == "CompactAdapter"
    assert QiskitExporter.__name__ == "QiskitExporter"


def test_algorithms_export_existing_functions():
    from quantum_cq.algorithms import bv_function, dj_function, twobit_block, twobit_function

    assert callable(twobit_function)
    assert callable(twobit_block)
    assert callable(dj_function)
    assert callable(bv_function)



def test_runtime_factory_creates_ideal_runtime():
    from quantum_cq.runtime import Mode, QuantumRuntime, RuntimeFactory
    runtime = RuntimeFactory.create(Mode.IDEAL)

    assert isinstance(runtime, QuantumRuntime)
    assert runtime.backend is not None
    assert runtime.sampler is not None
    assert runtime.service is None
    assert runtime.noise_model is None


def test_runtime_factory_accepts_ideal_as_string():
    from quantum_cq.runtime import Mode, QuantumRuntime, RuntimeFactory
    runtime = RuntimeFactory.create("ideal")

    assert isinstance(runtime, QuantumRuntime)
    assert runtime.backend is not None
    assert runtime.sampler is not None


def test_runtime_factory_create_many_preserves_mode_order(monkeypatch):
    from types import SimpleNamespace

    from quantum_cq.runtime import Mode, QuantumRuntime, RuntimeFactory

    def fake_create(mode, **kwargs):
        return QuantumRuntime(
            backend=SimpleNamespace(name=f"{mode.value}_backend"),
            sampler=FakeSampler(),
        )

    monkeypatch.setattr(RuntimeFactory, "create", staticmethod(fake_create))

    runtimes = RuntimeFactory.create_many(
        [Mode.IDEAL, "noisy"],
        parallel=True,
        max_workers=2,
    )

    assert list(runtimes) == [Mode.IDEAL, Mode.NOISY]
    assert runtimes[Mode.IDEAL].backend.name == "ideal_backend"
    assert runtimes[Mode.NOISY].backend.name == "noisy_backend"


def test_runtime_factory_accepts_direct_runtime_parameters(monkeypatch):
    from types import SimpleNamespace

    import quantum_cq.runtime as runtime_module
    from quantum_cq.runtime import Mode, RuntimeFactory

    captured = {}

    def fake_service(settings):
        captured["service_settings"] = settings
        return SimpleNamespace()

    def fake_get_real_backend(service, *, settings=None):
        captured["backend_settings"] = settings
        return SimpleNamespace(name="fake_real_backend")

    monkeypatch.setattr(RuntimeFactory, "_service", staticmethod(fake_service))
    monkeypatch.setattr(
        RuntimeFactory,
        "_get_real_backend",
        staticmethod(fake_get_real_backend),
    )
    monkeypatch.setattr(
        runtime_module,
        "SamplerV2",
        lambda mode: FakeSampler(),
    )

    runtime = RuntimeFactory.create(
        Mode.REAL,
        ibm_channel="ibm_cloud",
        ibm_token="token-direto",
        max_retries=1,
        wait_seconds=0,
    )

    assert runtime.backend.name == "fake_real_backend"
    assert captured["service_settings"].ibm_token == "token-direto"
    assert captured["backend_settings"].max_retries == 1


def test_configure_logging_writes_to_terminal(capsys):
    from quantum_cq import configure_logging

    configure_logging(level="INFO")
    logger = logging.getLogger("quantum_cq.test")

    logger.info("evento de teste")
    for handler in logging.getLogger("quantum_cq").handlers:
        handler.flush()

    captured = capsys.readouterr()
    assert "evento de teste" in captured.out
    assert all(not isinstance(handler, logging.FileHandler) for handler in logging.getLogger("quantum_cq").handlers)


def test_settings_read_external_environment(monkeypatch):
    from quantum_cq.settings import get_pipeline_settings, get_runtime_settings

    monkeypatch.setenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform")
    monkeypatch.setenv("IBM_QUANTUM_TOKEN", "token-de-teste")
    monkeypatch.setenv("QUANTUM_CQ_MODES", "ideal,real")
    monkeypatch.setenv("QUANTUM_CQ_REAL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("QUANTUM_CQ_CANCEL_REAL_ON_TIMEOUT", "true")

    runtime_settings = get_runtime_settings()
    pipeline_settings = get_pipeline_settings()

    assert runtime_settings.ibm_channel == "ibm_quantum_platform"
    assert runtime_settings.ibm_token == "token-de-teste"
    assert pipeline_settings.modes == ("ideal", "real")
    assert pipeline_settings.real_timeout_seconds == 30
    assert pipeline_settings.cancel_real_on_timeout is True


def test_runtime_settings_default_channel_matches_cloud_flow():
    from quantum_cq.settings import RuntimeSettings

    assert RuntimeSettings().ibm_channel == "ibm_quantum_platform"


def test_runtime_factory_rejects_ibm_cloud_channel_as_instance():
    from quantum_cq.runtime import RuntimeFactory
    from quantum_cq.settings import RuntimeSettings

    settings = RuntimeSettings(
        ibm_channel="ibm_cloud",
        ibm_token="token-direto",
        ibm_instance="ibm_cloud",
    )

    with pytest.raises(ValueError, match="Nao use 'ibm_cloud' como instance"):
        RuntimeFactory._validate_ibm_account_settings(settings)


def test_runtime_factory_resolves_ibm_instance_dynamically(monkeypatch):
    from quantum_cq.runtime import RuntimeFactory
    from quantum_cq.settings import RuntimeSettings

    settings = RuntimeSettings(
        ibm_channel="ibm_cloud",
        ibm_token="token-direto",
        ibm_instance=None,
    )

    assert RuntimeFactory._resolve_ibm_instance(settings) is None

    monkeypatch.setenv("IBM_QUANTUM_INSTANCE", "crn:v1:example")

    assert RuntimeFactory._resolve_ibm_instance(settings) == "crn:v1:example"


def test_cq_pipeline_encodes_data_with_default_registry():
    from quantum_cq import CQ

    encoded = CQ.pipeline().with_data([1, 0, 1]).with_encoding("basis").build()

    assert encoded.encoding_name == "basis"
    assert encoded.metadata["bitstring"] == "101"
    assert encoded.circuit.num_qubits == 3


def test_cq_pipeline_accepts_injected_registry():
    from quantum_cq import CQ
    from quantum_cq.handlers import HandlerRegistry
    from quantum_cq.results import EncodedCircuit

    class CustomEncoder:
        name = "custom"
        family = "custom"
        auto_selectable = False

        def can_handle(self, data):
            return data.value == [42]

        def encode(self, data):
            return EncodedCircuit(
                circuit=object(),
                metadata={
                    "encoding_name": self.name,
                    "num_qubits": 0,
                    "input_size": 1,
                    "family": "custom",
                },
                encoding_name=self.name,
            )

    registry = HandlerRegistry()
    registry.register(CustomEncoder())

    encoded = CQ.pipeline(registry=registry).with_data([42]).with_encoding("custom").run()

    assert encoded.encoding_name == "custom"
    assert encoded.metadata["family"] == "custom"


def test_cq_pipeline_with_encoding_uses_registry_not_selector():
    from quantum_cq import CQ
    from quantum_cq.handlers import HandlerRegistry
    from quantum_cq.results import EncodedCircuit

    class CustomEncoder:
        name = "custom"
        family = "custom"
        auto_selectable = False

        def can_handle(self, data):
            return True

        def encode(self, data):
            return EncodedCircuit(
                circuit=object(),
                metadata={
                    "encoding_name": self.name,
                    "num_qubits": 0,
                    "input_size": 1,
                    "family": "custom",
                },
                encoding_name=self.name,
            )

    class ExplodingSelector:
        def select(self, data):
            raise AssertionError("manual encoding should not use selector")

    registry = HandlerRegistry()
    registry.register(CustomEncoder())

    encoded = (
        CQ.pipeline(registry=registry, selector=ExplodingSelector())
        .with_data([42])
        .with_encoding("custom")
        .build()
    )

    assert encoded.encoding_name == "custom"


def test_cq_pipeline_auto_encoding_uses_selector():
    from quantum_cq import CQ
    from quantum_cq.handlers import default_encoding_registry

    class RecordingSelector:
        def __init__(self):
            self.called = False

        def select(self, data):
            self.called = True
            return default_encoding_registry().get("basis")

    selector = RecordingSelector()

    encoded = CQ.pipeline(selector=selector).with_data([1, 0, 1]).auto_encoding().build()

    assert selector.called is True
    assert encoded.encoding_name == "basis"


def test_cq_facade_encode_auto_encode_and_available_encodings():
    from quantum_cq import CQ
    from quantum_cq.results import EncodedCircuit

    manual = CQ.encode([1, 0, 1], encoding="basis")
    automatic = CQ.auto_encode([0.1, 0.2, 0.3])

    assert isinstance(manual, EncodedCircuit)
    assert isinstance(automatic, EncodedCircuit)
    assert manual.encoding_name == "basis"
    assert automatic.encoding_name == "angle"
    assert "basis" in CQ.available_encodings()


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    names = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            modules.add(module)
            for alias in node.names:
                names.add((module, alias.name))

    return modules, names


def _top_level_imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    names = set()

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            modules.add(module)
            for alias in node.names:
                names.add((module, alias.name))

    return modules, names


def test_architecture_boundaries_keep_qiskit_out_of_contracts_and_encoders():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "quantum_cq"

    interface_modules, _ = _imported_modules(package / "_core" / "interfaces.py")
    encoding_modules, encoding_imports = _imported_modules(package / "_encodings" / "state.py")
    selector_modules, _ = _imported_modules(package / "_core" / "selectors.py")
    oracle_modules, _ = _imported_modules(package / "_circuits" / "oracles.py")
    primitive_modules, _ = _imported_modules(package / "_circuits" / "primitives.py")
    navigation_top_modules, _ = _top_level_imported_modules(package / "_navigation" / "memory.py")
    walks_top_modules, _ = _top_level_imported_modules(package / "_navigation" / "walks.py")
    algorithm_top_modules, algorithm_top_imports = _top_level_imported_modules(
        package / "_algorithms" / "standard.py"
    )
    pipeline_tree = ast.parse((package / "_runtime" / "pipeline.py").read_text(encoding="utf-8"))
    _, pipeline_imports = _imported_modules(package / "_runtime" / "pipeline.py")

    assert "qiskit" not in interface_modules
    assert ".results" not in interface_modules
    assert "qiskit" not in encoding_modules
    assert "qiskit" not in oracle_modules
    assert "qiskit" not in primitive_modules
    assert "qiskit" not in navigation_top_modules
    assert "qiskit" not in walks_top_modules
    assert "qiskit" not in algorithm_top_modules
    assert ("qiskit", "QuantumCircuit") not in algorithm_top_imports
    assert ("qiskit", "QuantumCircuit") not in pipeline_imports
    assert not any(
        isinstance(node, ast.Name) and node.id == "QuantumCircuit"
        for node in ast.walk(pipeline_tree)
    )
    assert ".adapters" not in encoding_modules
    assert "quantum_cq.adapters" not in encoding_modules
    assert ("importlib", "import_module") not in encoding_imports
    assert ".encodings" not in selector_modules


def test_public_single_module_shims_preserve_module_identity():
    import importlib

    pairs = (
        ("quantum_cq.runtime", "quantum_cq._runtime.runtime"),
        ("quantum_cq.pipeline", "quantum_cq._runtime.pipeline"),
        ("quantum_cq.compact", "quantum_cq._circuits.compact"),
        ("quantum_cq.adapters", "quantum_cq._circuits.adapters"),
        ("quantum_cq.algorithms", "quantum_cq._algorithms.standard"),
        ("quantum_cq.encodings", "quantum_cq._encodings.state"),
        ("quantum_cq.experiment", "quantum_cq._runtime.experiment"),
        ("quantum_cq.config", "quantum_cq._runtime.config"),
    )

    for public_name, internal_name in pairs:
        public_module = importlib.import_module(public_name)
        internal_module = importlib.import_module(internal_name)
        assert public_module is internal_module


def test_public_aggregator_shims_expose_expected_symbols():
    import quantum_cq.core as core
    import quantum_cq.navigation as navigation

    assert core.CQ is not None
    assert core.QuantumData is not None
    assert core.EncodedCircuit is not None
    assert core.EncodingProtocol is not None

    assert navigation.AddressedMemory is not None
    assert navigation.GraphData is not None
    assert navigation.GraphNavigationEncoding is not None
    assert navigation.CoinedQuantumWalkPrimitive is not None


def test_private_modules_do_not_import_public_shims():
    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "quantum_cq"
    public_shims = {
        "adapters",
        "algorithms",
        "compact",
        "config",
        "core",
        "data",
        "encodings",
        "environment",
        "experiment",
        "handlers",
        "interfaces",
        "logging_config",
        "metrics",
        "navigation",
        "oracles",
        "pipeline",
        "primitives",
        "results",
        "runtime",
        "selectors",
        "settings",
        "walks",
    }

    for private_root in (
        "_core",
        "_circuits",
        "_encodings",
        "_navigation",
        "_algorithms",
        "_runtime",
        "_tools",
    ):
        for path in (package / private_root).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if parts[:1] == ["quantum_cq"] and len(parts) > 1:
                            assert parts[1].startswith("_"), (path, alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if node.level and module in public_shims:
                        assert False, (path, f"{'.' * node.level}{module}")
                    if module.startswith("quantum_cq."):
                        parts = module.split(".")
                        assert len(parts) > 1 and parts[1].startswith("_"), (path, module)


def test_config_and_environment_imports_have_no_creation_side_effects():
    import importlib

    root = Path(__file__).resolve().parents[1]
    package = root / "src" / "quantum_cq"

    config = (package / "_runtime" / "config.py").read_text(encoding="utf-8")
    environment = (package / "_core" / "environment.py").read_text(encoding="utf-8")

    assert "pipeline = create_pipeline()" not in config
    assert 'if __name__ == "__main__":' in environment

    config_module = importlib.import_module("quantum_cq.config")
    environment_module = importlib.import_module("quantum_cq.environment")

    assert not hasattr(config_module, "pipeline")
    assert callable(environment_module.setup_environment)
