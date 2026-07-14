import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from qiskit import QuantumCircuit

from quantum_cq import CQ, ExecutionContext, ExecutionTarget, TargetDatum, TargetStateSnapshot
from quantum_cq._engines.errors import CapabilityMismatchError
from quantum_cq._hardware.bundle import HardwareProviderBundle
from quantum_cq._hardware.models import ExecutionTargetDescriptor, NativeInstruction, TargetArchitecture
from quantum_cq._hardware.providers.qiskit import target_from_qiskit
from quantum_cq._hardware.service import HardwareService


class _ProviderPort:
    def __init__(self, provider_id="fake"):
        self.provider_id = provider_id

    def list_targets(self):
        return ()

    def architecture(self, descriptor):
        return TargetArchitecture("fake", ("q0",))

    def snapshot(self, descriptor):
        return None


def _measured_bell():
    circuit = CQ.circuit(2, 2, name="bell")
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure(0, 0)
    circuit.measure(1, 1)
    return circuit


def test_manual_target_is_sdk_free_classified_and_has_provenance():
    target = CQ.manual_target(
        target_id="ideal2",
        qubits=2,
        operations=["x", "h", "cx", "measure"],
        target_type="simulator_ideal",
    )

    assert isinstance(target, ExecutionTarget)
    assert target.descriptor.target_type == "simulator_ideal"
    assert target.architecture.num_qubits == 2
    assert target.provenance is not None
    assert target.provenance.source == "manual"
    assert "user-declared" in target.provenance.warnings[0]


def test_hardware_models_preserve_absence_and_immutability():
    datum = TargetDatum("unknown", reason="provider omitted value")
    snapshot = TargetStateSnapshot(
        snapshot_id="s1",
        target_id="t1",
        collected_at=datetime.now(timezone.utc) - timedelta(days=2),
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
        qubit_properties={"q0": {"t1": datum}},
    )

    assert snapshot.stale is True
    assert snapshot.qubit_properties["q0"]["t1"].status == "unknown"
    with pytest.raises(TypeError):
        snapshot.qubit_properties["q1"] = {}


def test_hardware_provider_bundle_rejects_mixed_provider_ports():
    with pytest.raises(ValueError, match="providers diferentes"):
        HardwareProviderBundle(
            provider_id="fake",
            discovery=_ProviderPort("fake"),
            architecture=_ProviderPort("other"),
            snapshot=_ProviderPort("fake"),
        )


def test_hardware_service_serializes_and_deserializes_neutral_target():
    service = HardwareService()
    target = service.manual_target(
        target_id="noisy",
        qubits=("a", "b"),
        operations=("x", "cx", "measure"),
        target_type="simulator_noisy",
    )

    payload = service.serialize(target)
    restored = service.deserialize(payload)

    assert payload["schema_version"] == "run3.hardware.v1"
    assert restored.descriptor.target_id == "noisy"
    assert restored.architecture.qubits == ("a", "b")


def test_qiskit_provider_uses_explicit_object_without_remote_discovery():
    native = QuantumCircuit(2, 2)
    native.h(0)
    native.cx(0, 1)
    native.measure(0, 0)
    qiskit_target = target_from_qiskit(native, name="explicit_circuit")

    assert qiskit_target.descriptor.provider == "qiskit"
    assert qiskit_target.descriptor.name == "explicit_circuit"
    assert qiskit_target.provenance.source == "explicit_object"
    assert qiskit_target.architecture.num_qubits == 2


def test_compile_records_execution_context_without_claiming_physical_execution():
    target = CQ.manual_target(
        target_id="ideal2",
        qubits=2,
        operations=["x", "h", "cx", "measure"],
        target_type="simulator_ideal",
    )

    compiled = CQ.compile(_measured_bell(), engine="qiskit", target=target)

    assert isinstance(compiled.context, ExecutionContext)
    assert compiled.context.target is target
    assert compiled.compatibility_report.target is target
    assert compiled.compatibility_report.physical_execution_claimed is False
    assert compiled.target_fingerprint == target.architecture.fingerprint


def test_compatibility_reports_insufficient_target_qubits_separately():
    target = CQ.manual_target(
        target_id="too_small",
        qubits=1,
        operations=["x", "h", "cx", "measure"],
        target_type="simulator_ideal",
    )

    report = CQ.compatibility(_measured_bell(), engine="qiskit", target=target)

    assert report.status == "incompatible"
    assert "target_qubits" in report.missing
    assert report.physical_execution_claimed is False


def test_run_engine_rejects_physical_target_before_sdk_execution():
    target = CQ.manual_target(
        target_id="manual_physical",
        qubits=2,
        operations=["x", "h", "cx", "measure"],
        target_type="physical",
    )

    with pytest.raises(CapabilityMismatchError, match="target fisico"):
        CQ.run_engine(_measured_bell(), engine="qiskit", target=target, shots=4)


def test_hardware_domain_and_service_do_not_import_sdks_or_circuit_concretes():
    checked = (
        Path("src/quantum_cq/_hardware/models.py"),
        Path("src/quantum_cq/_hardware/service.py"),
        Path("src/quantum_cq/_hardware/protocols.py"),
    )
    forbidden_roots = {"qiskit", "cirq", "pennylane", "braket", "cudaq"}
    for path in checked:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not forbidden_roots.intersection(imports), path


def test_engine_service_does_not_import_concrete_providers():
    path = Path("src/quantum_cq/_engines/service.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "quantum_cq._hardware.providers.qiskit" not in imported
