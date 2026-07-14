import os
import subprocess
import sys
import textwrap
import ast
from pathlib import Path

import pytest

from quantum_cq import CQ, CatalogEntry
from quantum_cq._core.compatibility import ComponentRequirement
from quantum_cq._core.components import ComponentDescriptor, ComponentService
from quantum_cq._core.handlers import FactoryRegistry
from quantum_cq.adapters import LogicalCircuitFactory


def test_cq_oracle_forwards_construction_args_and_returns_new_instances():
    first = CQ.oracle("deutsch", case=2)
    second = CQ.oracle("deutsch", case=3)

    assert first.case == 2
    assert second.case == 3
    assert first is not second


def test_cq_oracle_applies_circuit_factory_for_oracles_that_build_circuits():
    oracle = CQ.oracle(
        "phase_marked_state",
        marked_state="11",
        circuit_factory=LogicalCircuitFactory(),
    )
    built = oracle.build()

    assert built.circuit_format == "ir"
    assert built.metadata["oracle_name"] == "phase_marked_state"


def test_cq_oracle_errors_are_clear_for_invalid_args():
    with pytest.raises(TypeError, match="Argumentos invalidos"):
        CQ.oracle("deutsch", unknown=True)


def test_catalog_returns_read_only_entries_derived_from_registry_descriptors():
    entries = CQ.catalog(category="oracle", name="phase_marked_state")

    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, CatalogEntry)
    assert entry.name == "phase_marked_state"
    assert entry.category == "oracle"
    assert entry.access_path.startswith("CQ.oracle")
    assert [requirement.feature for requirement in entry.requirements] == ["x", "h", "mcx"]

    with pytest.raises(TypeError):
        entry.metadata["new"] = "forbidden"


def test_catalog_does_not_execute_factories_to_describe_components():
    registry = FactoryRegistry()
    registry.register(
        "exploding",
        lambda: (_ for _ in ()).throw(AssertionError("factory executed")),
        descriptor=ComponentDescriptor(
            name="exploding",
            category="oracle",
            access_path="CQ.oracle('exploding')",
        ),
    )
    service = ComponentService(oracle_registry=registry)

    entries = service.catalog(category="oracle", name="exploding")

    assert len(entries) == 1
    assert entries[0].name == "exploding"


def test_catalog_filters_by_engine_using_declared_requirements():
    qiskit_entries = CQ.catalog(category="algorithm", name="deutsch", engine="qiskit")
    braket_entries = CQ.catalog(category="primitive", name="qft", engine="braket")

    assert [entry.name for entry in qiskit_entries] == ["deutsch"]
    assert [entry.name for entry in braket_entries] == ["qft"]
    assert braket_entries[0].compatibility is not None
    assert braket_entries[0].compatibility.status in {"incompatible", "not_tested"}


def test_catalog_does_not_instantiate_default_encoders(monkeypatch):
    import quantum_cq._core.handlers as handlers

    def explode(*args, **kwargs):
        raise AssertionError("default encoding registry instantiated")

    monkeypatch.setattr(handlers, "default_encoding_registry", explode)
    service = ComponentService()

    entries = service.catalog(category="encoding", name="basis")

    assert [entry.name for entry in entries] == ["basis"]


def test_catalog_preserves_advanced_requirement_descriptors():
    registry = FactoryRegistry()
    registry.register(
        "advanced",
        lambda: object(),
        descriptor=ComponentDescriptor(
            name="advanced",
            category="primitive",
            requirements=(
                ComponentRequirement(
                    "mcx",
                    alternatives=("ccx",),
                    allow_lowered=False,
                    description="native multi-control requirement",
                    category="gate",
                ),
            ),
        ),
    )
    service = ComponentService(primitive_registry=registry)

    entry = service.catalog(category="primitive", name="advanced")[0]

    assert entry.requirements[0].feature == "mcx"
    assert entry.requirements[0].alternatives == ("ccx",)
    assert entry.requirements[0].allow_lowered is False
    assert entry.requirements[0].category == "gate"


def test_catalog_does_not_load_optional_engine_sdks_on_root_use():
    env = dict(os.environ)
    src = os.path.abspath("src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else os.pathsep.join([src, env["PYTHONPATH"]])
    snippet = textwrap.dedent(
        """
        import sys
        from quantum_cq import CQ

        CQ.catalog()
        optional = ("pennylane", "cirq", "braket", "cudaq", "qiskit_aer", "qiskit_ibm_runtime")
        loaded = [name for name in optional if any(module == name or module.startswith(name + ".") for module in sys.modules)]
        assert not loaded, loaded
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", snippet],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_component_service_does_not_import_engine_implementations():
    path = Path("src/quantum_cq/_core/components.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not any(module.startswith("quantum_cq._engines") for module in imported)


def test_representative_components_can_be_built_logically_for_optional_engines():
    state = CQ.state([1, 0], engine="cirq")
    oracle = CQ.oracle("phase_marked_state", marked_state="11", engine="cirq").build()
    diffuser = CQ.diffuser(2, engine="cirq")
    deutsch = CQ.deutsch(case=2, engine="cirq")
    navigation = CQ.nav([1, 2], quantum_engine="cirq")

    assert state.metadata["circuit_format"] == "ir"
    assert oracle.circuit_format == "ir"
    assert diffuser.circuit_format == "ir"
    assert deutsch.circuit_format == "ir"
    assert navigation.circuit_format == "ir"

    assert oracle.metadata["oracle_name"] == "phase_marked_state"
    assert diffuser.metadata["operator_name"] == "standard_diffuser"
    assert deutsch.metadata["algorithm_name"] == "deutsch"
    assert navigation.metadata["navigation_name"] == "addressed_memory"
