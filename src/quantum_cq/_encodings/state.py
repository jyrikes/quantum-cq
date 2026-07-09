"""Strategies concretas de encoding."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from numbers import Integral, Real
from typing import Any

import numpy as np

from quantum_cq._core.data import QuantumData
from quantum_cq._core.interfaces import CircuitBuilderProtocol, CircuitFactoryProtocol, EncodingProtocol
from quantum_cq._core.results import EncodedCircuit


def _unwrap_data(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, QuantumData):
        return data.value, dict(data.metadata)

    return data, {}


def _to_sequence(value: Any) -> list[Any]:
    if isinstance(value, (str, bytes)):
        raise TypeError("Sequencias de encoding nao podem ser strings")

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, Iterable):
        return list(value)

    raise TypeError("O valor de entrada deve ser uma sequencia")


def _is_binary_scalar(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, Integral) and int(value) in {0, 1}


def _is_numeric_scalar(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def _is_binary_sequence(values: Sequence[Any]) -> bool:
    return bool(values) and all(_is_binary_scalar(value) for value in values)


def _is_numeric_sequence(values: Sequence[Any]) -> bool:
    return bool(values) and all(_is_numeric_scalar(value) for value in values)


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


def _apply_axis(builder: CircuitBuilderProtocol, axis: str, angle: float, qubit: int) -> None:
    if axis == "x":
        builder.rx(angle, qubit)
        return

    if axis == "y":
        builder.ry(angle, qubit)
        return

    if axis == "p":
        builder.p(angle, qubit)
        return

    builder.rz(angle, qubit)


def _apply_pairwise_zz(builder: CircuitBuilderProtocol, values: Sequence[float]) -> None:
    for index in range(len(values) - 1):
        theta = 2.0 * float(values[index]) * float(values[index + 1])
        builder.cx(index, index + 1)
        builder.rz(theta, index + 1)
        builder.cx(index, index + 1)


class _BaseEncoding(EncodingProtocol):
    name = ""
    family = ""
    auto_selectable = False

    def __init__(self, circuit_factory: CircuitFactoryProtocol | None = None) -> None:
        if circuit_factory is None:
            raise ValueError("circuit_factory e obrigatoria para encoders")

        self.circuit_factory = circuit_factory

    def _builder(self, num_qubits: int) -> CircuitBuilderProtocol:
        return self.circuit_factory.create(num_qubits)

    def _encoded(
        self,
        builder: CircuitBuilderProtocol,
        metadata: dict[str, Any],
        *,
        num_qubits: int,
        input_size: int,
        **extra: Any,
    ) -> EncodedCircuit:
        metadata.update(
            {
                "encoding_name": self.name,
                "family": self.family,
                "num_qubits": num_qubits,
                "input_size": input_size,
                **extra,
            }
        )
        return EncodedCircuit(
            circuit=builder.build(),
            metadata=metadata,
            encoding_name=self.name,
        )


class BasisEncoding(_BaseEncoding):
    name = "basis"
    family = "basis"
    auto_selectable = True

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_binary_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("BasisEncoding aceita apenas sequencias binarias")

        bitstring = "".join(str(int(bit)) for bit in values)
        builder = self._builder(len(values))
        gates_applied: list[str] = []

        for index, bit in enumerate(values):
            if int(bit) == 1:
                builder.x(index)
                gates_applied.append("x")

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            bitstring=bitstring,
            gates_applied=gates_applied,
        )


class AngleEncoding(_BaseEncoding):
    name = "angle"
    family = "rotation"
    auto_selectable = True

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values) and not _is_binary_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("AngleEncoding requer sequencia numerica nao binaria")

        builder = self._builder(len(values))
        for index, angle in enumerate(values):
            builder.ry(float(angle), index)

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            rotation_axis="ry",
        )


class DenseAngleEncoding(_BaseEncoding):
    name = "dense_angle"
    family = "rotation"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values) and not _is_binary_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("DenseAngleEncoding requer sequencia numerica nao binaria")

        num_qubits = max(1, math.ceil(len(values) / 2))
        builder = self._builder(num_qubits)
        padded = list(values) + [0.0] * ((num_qubits * 2) - len(values))

        # Dois angulos por qubit.
        for qubit in range(num_qubits):
            builder.ry(float(padded[2 * qubit]), qubit)
            builder.rz(float(padded[2 * qubit + 1]), qubit)

        return self._encoded(
            builder,
            metadata,
            num_qubits=num_qubits,
            input_size=len(values),
            features_per_qubit=2,
        )


class PhaseEncoding(_BaseEncoding):
    name = "phase"
    family = "rotation"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("PhaseEncoding requer sequencia numerica")

        builder = self._builder(len(values))
        for index, angle in enumerate(values):
            builder.p(float(angle), index)

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            gate="p",
        )


class ZFeatureMapEncoding(_BaseEncoding):
    name = "z_feature_map"
    family = "feature_map"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("ZFeatureMapEncoding requer sequencia numerica")

        builder = self._builder(len(values))
        # Base com Hadamard.
        for qubit in range(len(values)):
            builder.h(qubit)
        for qubit, angle in enumerate(values):
            builder.p(float(angle), qubit)

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            feature_map="z",
        )


class ZZFeatureMapEncoding(_BaseEncoding):
    name = "zz_feature_map"
    family = "feature_map"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("ZZFeatureMapEncoding requer sequencia numerica")

        builder = self._builder(len(values))
        # Base com Hadamard.
        for qubit in range(len(values)):
            builder.h(qubit)
        for qubit, angle in enumerate(values):
            builder.p(float(angle), qubit)
        # Interacao ZZ simples.
        _apply_pairwise_zz(builder, [float(item) for item in values])

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            feature_map="zz",
        )


class PauliFeatureMapEncoding(_BaseEncoding):
    name = "pauli_feature_map"
    family = "feature_map"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("PauliFeatureMapEncoding requer sequencia numerica")

        paulis = [str(item).lower() for item in metadata.get("paulis", ["z", "zz"])]
        invalid_paulis = [pauli for pauli in paulis if pauli not in {"x", "y", "z", "zz"}]
        if invalid_paulis:
            raise ValueError(f"PauliFeatureMapEncoding recebeu pauli invalido: {invalid_paulis[0]}")

        builder = self._builder(len(values))

        # Base com Hadamard.
        for qubit in range(len(values)):
            builder.h(qubit)

        for pauli in paulis:
            if pauli == "zz":
                _apply_pairwise_zz(builder, [float(item) for item in values])
                continue

            for qubit, angle in enumerate(values):
                _apply_axis(builder, pauli, float(angle), qubit)

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            feature_map="pauli",
            paulis=paulis,
        )


class IQPEncoding(_BaseEncoding):
    name = "iqp"
    family = "feature_map"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("IQPEncoding requer sequencia numerica")

        builder = self._builder(len(values))
        # Camada de entrada.
        for qubit in range(len(values)):
            builder.h(qubit)

        # Fase diagonal.
        for qubit, angle in enumerate(values):
            builder.p(float(angle), qubit)

        # Interacao e saida.
        _apply_pairwise_zz(builder, [float(item) for item in values])

        for qubit in range(len(values)):
            builder.h(qubit)

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            feature_map="iqp",
        )


class DataReUploadingEncoding(_BaseEncoding):
    name = "data_reuploading"
    family = "feature_map"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values)

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("DataReUploadingEncoding requer sequencia numerica")

        repetitions = int(metadata.get("repetitions", 2))
        if repetitions <= 0:
            raise ValueError("DataReUploadingEncoding requer repetitions positive")

        builder = self._builder(len(values))
        # Reaplica os dados por camada.
        for layer in range(repetitions):
            for qubit, angle in enumerate(values):
                builder.ry(float(angle), qubit)

            if layer < repetitions - 1:
                builder.barrier()

        return self._encoded(
            builder,
            metadata,
            num_qubits=len(values),
            input_size=len(values),
            num_layers=repetitions,
            repetitions=repetitions,
        )


# Alias legado; nao participa do registry padrao.
class FeatureMapEncoder(ZFeatureMapEncoding):
    name = "feature_map"
    family = "feature_map"
    auto_selectable = False


class AmplitudeEncoding(_BaseEncoding):
    name = "amplitude"
    family = "amplitude"
    auto_selectable = False

    def can_handle(self, data: Any) -> bool:
        value, _ = _unwrap_data(data)
        try:
            values = _to_sequence(value)
        except TypeError:
            return False

        return _is_numeric_sequence(values) and len(values) > 0 and _is_power_of_two(len(values))

    def encode(self, data: Any) -> EncodedCircuit:
        value, metadata = _unwrap_data(data)
        values = _to_sequence(value)

        if not self.can_handle(data):
            raise ValueError("AmplitudeEncoding requer sequencia numerica com tamanho potencia de 2")

        amplitudes = np.asarray(values, dtype=complex)
        norm = float(np.linalg.norm(amplitudes))
        if norm == 0:
            raise ValueError("AmplitudeEncoding requer vetor nao nulo")

        normalized = not np.isclose(norm, 1.0)
        if normalized:
            amplitudes = amplitudes / norm

        num_qubits = int(math.log2(len(amplitudes)))
        builder = self._builder(num_qubits)
        builder.initialize(amplitudes.tolist(), list(range(num_qubits)))

        return self._encoded(
            builder,
            metadata,
            num_qubits=num_qubits,
            input_size=len(values),
            normalized=normalized,
            norm=norm,
        )
