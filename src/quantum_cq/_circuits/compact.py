# ============================================================
# Módulo CQ compacto: circuito tabular isolado + adapter + exporter
# ============================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from quantum_cq._circuits.unitary import CustomUnitary, unitary_payload

if TYPE_CHECKING:
    import pandas as pd


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "Para usar QC.df ou QC.show, instale quantum-cq[notebook]."
        ) from exc

    return pd


# ============================================================
# Erros
# ============================================================

class CircuitError(Exception):
    pass


class CircuitParseError(CircuitError):
    pass


class CircuitValidationError(CircuitError):
    pass


# ============================================================
# Tokens compactos para escrita da matriz
# ============================================================

@dataclass(frozen=True)
class Control:
    gate: str
    id: str = "0"


@dataclass(frozen=True)
class Target:
    gate: str
    id: str = "0"


@dataclass(frozen=True)
class Observe:
    name: str = "obs"


@dataclass(frozen=True)
class Separator:
    name: str = "sep"


@dataclass(frozen=True)
class Measure:
    bit: int = 0


def ctrl(gate: str, id: str = "0") -> Control:
    return Control(gate.upper(), id)


def tgt(gate: str, id: str = "0") -> Target:
    return Target(gate.upper(), id)


def obs(name: str = "obs") -> Observe:
    return Observe(name)


def sep(name: str = "sep") -> Separator:
    return Separator(name)


def m(bit: int = 0) -> Measure:
    return Measure(bit)


# ============================================================
# Registro de portas nativas e customizadas
# ============================================================

@dataclass(frozen=True)
class GateDef:
    name: str
    kind: str
    arity: int = 1
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None


class Gates:
    def __init__(self):
        self._items: dict[str, GateDef] = {}
        for name in ("H", "X", "Y", "Z", "S", "T"):
            self.add(name, kind=name.lower())

    def add(
        self,
        name: str,
        *,
        kind: str | None = None,
        arity: int = 1,
        params: dict[str, Any] | None = None,
        matrix: Any | None = None,
        qiskit_gate: Any | None = None,
        label: str | None = None,
    ) -> "Gates":
        key = name.upper()
        data = dict(params or {})
        if matrix is not None:
            data["matrix"] = matrix
        if qiskit_gate is not None:
            data["qiskit_gate"] = qiskit_gate

        self._items[key] = GateDef(
            name=key,
            kind=kind or key.lower(),
            arity=arity,
            params=data,
            label=label or key,
        )
        return self

    def has(self, name: str) -> bool:
        return name.upper() in self._items

    def get(self, name: str) -> GateDef:
        key = name.upper()
        if key not in self._items:
            raise CircuitParseError(f"Porta não registrada: {name}")
        return self._items[key]


# ============================================================
# IR compacta
# ============================================================

@dataclass(frozen=True)
class QuantumState:
    kind: str
    value: Any
    qubits: tuple[int, ...]


@dataclass(frozen=True)
class Operation:
    kind: str
    qubits: tuple[int, ...] = ()
    clbits: tuple[int, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)
    label: str | None = None


@dataclass
class Layer:
    operations: list[Operation] = field(default_factory=list)

    def add(self, operation: Operation):
        if operation.qubits:
            used = {q for op in self.operations for q in op.qubits}
            conflict = used.intersection(operation.qubits)
            if conflict:
                raise CircuitValidationError(
                    f"Conflito na camada: qubit(s) {sorted(conflict)} já ocupado(s)."
                )
        self.operations.append(operation)


@dataclass
class CircuitIR:
    name: str
    n_qubits: int
    n_clbits: int
    inputs: list[QuantumState]
    layers: list[Layer]
    outputs: list[Operation]
    metadata: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Circuito tabular compacto
# ============================================================

class QC:
    """
    Circuito escrito como matriz.

    Se io=True:
        primeira coluna = input
        última coluna = output
        colunas internas = tempo lógico

    Se io=False:
        todas as colunas = tempo lógico

    Células aceitas:
        0, 1, "H", "X", gate customizada, ctrl("CX"), tgt("CX"),
        obs("nome"), sep("nome"), m(0), e outro QC como subcircuito.
    """

    def __init__(
        self,
        name: str,
        matrix: list[list[Any]],
        *,
        c: int | list[str] | None = None,
        gates: Gates | None = None,
        qubits: list[str] | None = None,
        io: bool = True,
    ):
        if not matrix:
            raise CircuitValidationError("A matriz não pode ser vazia.")

        width = len(matrix[0])
        if any(len(row) != width for row in matrix):
            raise CircuitValidationError("Todas as linhas precisam ter o mesmo tamanho.")

        self.name = name
        self.matrix = matrix
        self.io = io
        self.gates = gates or Gates()
        self.qubits = qubits or [f"q{i}" for i in range(len(matrix))]
        self.cbits = self._normalize_cbits(c)

        if io:
            if width < 2:
                raise CircuitValidationError("Com io=True, precisa haver input e output.")
            self.columns = ["input", *[f"t{i}" for i in range(width - 2)], "output"]
        else:
            self.columns = [f"t{i}" for i in range(width)]

    def _normalize_cbits(self, c: int | list[str] | None) -> list[str]:
        if c is None:
            return []
        if isinstance(c, int):
            if c < 0:
                raise CircuitValidationError("A quantidade de bits clássicos não pode ser negativa.")
            return [f"c{i}" for i in range(c)]
        for bit in c:
            if not re.fullmatch(r"c\d+", bit):
                raise CircuitValidationError(f"Bit clássico inválido: {bit}")
        return c

    @property
    def df(self) -> pd.DataFrame:
        pd = _require_pandas()
        return pd.DataFrame(
            [[self._display_cell(cell) for cell in row] for row in self.matrix],
            index=self.qubits,
            columns=self.columns,
        )

    def show(self) -> pd.DataFrame:
        return self.df

    def to_ir(self) -> CircuitIR:
        return CompactAdapter().parse(self)

    def to_qiskit(self):
        return QiskitExporter().export(self.to_ir())

    def draw(self, *args: Any, **kwargs: Any):
        return self.to_qiskit().draw(*args, **kwargs)

    def _display_cell(self, cell: Any) -> str:
        if isinstance(cell, QC):
            return cell.name
        if isinstance(cell, Control):
            return f"{cell.gate}.ctrl({cell.id})"
        if isinstance(cell, Target):
            return f"{cell.gate}.tgt({cell.id})"
        if isinstance(cell, Observe):
            return f"OBS({cell.name})"
        if isinstance(cell, Separator):
            return f"SEP({cell.name})"
        if isinstance(cell, Measure):
            return f"M{cell.bit}"
        return str(cell)


class LogicalCircuitBuilder:
    """Builder SDK-neutral backed by the existing CircuitIR."""

    target_format = "ir"

    def __init__(
        self,
        num_qubits: int,
        num_clbits: int = 0,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._num_qubits = num_qubits
        self._num_clbits = num_clbits
        self._name = name or "logical_circuit"
        self._metadata = dict(metadata or {})
        self._layers: list[Layer] = []

    def x(self, qubit: int) -> None:
        self._append(Operation("x", qubits=(qubit,)))

    def h(self, qubit: int) -> None:
        self._append(Operation("h", qubits=(qubit,)))

    def rx(self, theta: float, qubit: int) -> None:
        self._append(Operation("rx", qubits=(qubit,), params={"theta": theta}))

    def ry(self, theta: float, qubit: int) -> None:
        self._append(Operation("ry", qubits=(qubit,), params={"theta": theta}))

    def rz(self, theta: float, qubit: int) -> None:
        self._append(Operation("rz", qubits=(qubit,), params={"theta": theta}))

    def p(self, theta: float, qubit: int) -> None:
        self._append(Operation("p", qubits=(qubit,), params={"theta": theta}))

    def cx(self, control: int, target: int) -> None:
        self._append(
            Operation(
                "cx",
                qubits=(control, target),
                params={"control": control, "target": target},
            )
        )

    def cz(self, control: int, target: int) -> None:
        self._append(
            Operation(
                "cz",
                qubits=(control, target),
                params={"control": control, "target": target},
            )
        )

    def cp(self, theta: float, control: int, target: int) -> None:
        self._append(
            Operation(
                "cp",
                qubits=(control, target),
                params={"theta": theta, "control": control, "target": target},
            )
        )

    def mcx(self, controls: Sequence[int], target: int) -> None:
        controls_tuple = tuple(controls)
        self._append(
            Operation(
                "mcx",
                qubits=(*controls_tuple, target),
                params={"controls": controls_tuple, "target": target},
            )
        )

    def swap(self, left: int, right: int) -> None:
        self._append(Operation("swap", qubits=(left, right), params={"left": left, "right": right}))

    def unitary(self, matrix: Any, qubits: Sequence[int], label: str | None = None) -> None:
        qubits_tuple = tuple(qubits)
        payload = unitary_payload(matrix, qubits_tuple)
        operation_label = label or (matrix.name if isinstance(matrix, CustomUnitary) else None)
        self._append(Operation("unitary", qubits=qubits_tuple, params=payload, label=operation_label))

    def measure(self, qubit: int, clbit: int) -> None:
        self._num_clbits = max(self._num_clbits, clbit + 1)
        self._append(Operation("measure", qubits=(qubit,), clbits=(clbit,)))

    def barrier(self) -> None:
        self._append(Operation("barrier"))

    def initialize(self, amplitudes: Sequence[complex], qubits: Sequence[int]) -> None:
        self._append(
            Operation(
                "initialize",
                qubits=tuple(qubits),
                params={"amplitudes": tuple(amplitudes)},
            )
        )

    def measure_all(self) -> None:
        self._num_clbits = max(self._num_clbits, self._num_qubits)
        for qubit in range(self._num_qubits):
            self.measure(qubit, qubit)

    def compose(
        self,
        circuit_like: Any,
        *,
        qubit_map: dict[int, int] | None = None,
        clbit_map: dict[int, int] | None = None,
        label: str | None = None,
    ) -> None:
        sub_ir = _logical_ir_for_composition(circuit_like)
        qmap = _resolve_mapping(
            "qubit",
            size=sub_ir.n_qubits,
            target_size=self._num_qubits,
            mapping=qubit_map,
        )
        cmap = _resolve_mapping(
            "clbit",
            size=sub_ir.n_clbits,
            target_size=self._num_clbits,
            mapping=clbit_map,
        )
        origin = label or sub_ir.name
        for layer in sub_ir.layers:
            remapped = Layer()
            for operation in layer.operations:
                remapped.add(_remap_operation(operation, qmap, cmap, origin))
            self._layers.append(remapped)
        if sub_ir.outputs:
            output_layer = Layer()
            for operation in sub_ir.outputs:
                output_layer.add(_remap_operation(operation, qmap, cmap, origin))
            self._layers.append(output_layer)
        self._metadata.setdefault("subcircuits", []).append(origin)

    def build(self) -> CircuitIR:
        return CircuitIR(
            name=self._name,
            n_qubits=self._num_qubits,
            n_clbits=self._num_clbits,
            inputs=[],
            layers=list(self._layers),
            outputs=[],
            metadata=dict(self._metadata),
        )

    def _append(self, operation: Operation) -> None:
        layer = Layer()
        layer.add(operation)
        self._layers.append(layer)


class LogicalCircuitFactory:
    def create(
        self,
        num_qubits: int,
        num_clbits: int = 0,
        *,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LogicalCircuitBuilder:
        return LogicalCircuitBuilder(num_qubits, num_clbits, name=name, metadata=metadata)


def _logical_ir_for_composition(circuit_like: Any) -> CircuitIR:
    if isinstance(circuit_like, LogicalCircuitBuilder):
        return circuit_like.build()
    if isinstance(circuit_like, CircuitIR):
        return circuit_like
    if isinstance(circuit_like, QC):
        return CompactAdapter().parse(circuit_like)
    if hasattr(circuit_like, "circuit") and getattr(circuit_like, "circuit_format", None) == "ir":
        return _logical_ir_for_composition(circuit_like.circuit)
    if hasattr(circuit_like, "metadata") and getattr(circuit_like, "circuit", None) is not None:
        metadata = getattr(circuit_like, "metadata", {}) or {}
        if metadata.get("circuit_format") == "ir":
            return _logical_ir_for_composition(circuit_like.circuit)
    raise CircuitValidationError(
        f"Composicao logica requer CircuitIR/QC/builder/wrapper IR; recebido {type(circuit_like).__name__}"
    )


def _resolve_mapping(
    label: str,
    *,
    size: int,
    target_size: int,
    mapping: dict[int, int] | None,
) -> dict[int, int]:
    if size == 0:
        return {}
    if mapping is None:
        if size != target_size:
            raise CircuitValidationError(
                f"Mapeamento explicito de {label}s e obrigatorio quando os registradores diferem"
            )
        mapping = {index: index for index in range(size)}
    expected = set(range(size))
    if set(mapping) != expected:
        raise CircuitValidationError(f"Mapeamento de {label}s deve cobrir exatamente {sorted(expected)}")
    values = tuple(mapping[index] for index in range(size))
    if len(set(values)) != len(values):
        raise CircuitValidationError(f"Mapeamento de {label}s possui destinos duplicados")
    if any(value < 0 or value >= target_size for value in values):
        raise CircuitValidationError(f"Mapeamento de {label}s aponta para destino fora do intervalo")
    return dict(mapping)


def _remap_operation(
    operation: Operation,
    qubit_map: dict[int, int],
    clbit_map: dict[int, int],
    origin: str,
) -> Operation:
    qubits = tuple(qubit_map[index] for index in operation.qubits)
    clbits = tuple(clbit_map[index] for index in operation.clbits)
    params = dict(operation.params)
    if "control" in params:
        params["control"] = qubit_map[params["control"]]
    if "target" in params:
        params["target"] = qubit_map[params["target"]]
    if "controls" in params:
        params["controls"] = tuple(qubit_map[index] for index in params["controls"])
    if "left" in params:
        params["left"] = qubit_map[params["left"]]
    if "right" in params:
        params["right"] = qubit_map[params["right"]]
    if "target_order" in params:
        params["target_order"] = tuple(qubit_map[index] for index in params["target_order"])
    params.setdefault("origin", origin)
    return Operation(operation.kind, qubits=qubits, clbits=clbits, params=params, label=operation.label)


# ============================================================
# Adapter: QC -> CircuitIR
# ============================================================

class CompactAdapter:
    EMPTY = {"", "-", "--", ".", "I", None}

    def __init__(self):
        self._cache: dict[int, CircuitIR] = {}

    def parse(self, circuit: QC) -> CircuitIR:
        key = id(circuit)
        if key in self._cache:
            return self._cache[key]

        inputs = self._parse_inputs(circuit)
        layers = self._parse_layers(circuit)
        outputs, inferred_clbits = self._parse_outputs(circuit)

        declared_clbits = self._declared_clbit_count(circuit)
        n_clbits = max(declared_clbits, inferred_clbits)

        ir = CircuitIR(
            name=circuit.name,
            n_qubits=len(circuit.qubits),
            n_clbits=n_clbits,
            inputs=inputs,
            layers=layers,
            outputs=outputs,
        )
        self._cache[key] = ir
        return ir

    def _declared_clbit_count(self, circuit: QC) -> int:
        if not circuit.cbits:
            return 0
        return max(int(bit[1:]) for bit in circuit.cbits) + 1

    def _parse_inputs(self, circuit: QC) -> list[QuantumState]:
        if not circuit.io:
            return []
        states = []
        for q, row in enumerate(circuit.matrix):
            cell = row[0]
            if cell in self.EMPTY:
                continue
            if cell in (0, "0", "|0>"):
                states.append(QuantumState("ket", "0", (q,)))
                continue
            if cell in (1, "1", "|1>"):
                states.append(QuantumState("ket", "1", (q,)))
                continue
            if isinstance(cell, str):
                state = re.fullmatch(r"STATE\((\w+)\)", cell.strip())
                if state:
                    states.append(QuantumState("state", state.group(1), (q,)))
                    continue
            raise CircuitParseError(f"Entrada inválida em q{q}: {cell}")
        return states

    def _parse_outputs(self, circuit: QC) -> tuple[list[Operation], int]:
        if not circuit.io:
            return [], 0

        outputs = []
        max_bit = -1

        for q, row in enumerate(circuit.matrix):
            cell = row[-1]
            if cell in self.EMPTY:
                continue

            bit = None
            if isinstance(cell, Measure):
                bit = cell.bit
            elif isinstance(cell, str):
                token = cell.strip().upper()
                short = re.fullmatch(r"M(\d+)", token)
                if short:
                    bit = int(short.group(1))
                long = re.fullmatch(r"MEASURE\(C?(\d+)\)", token)
                if long:
                    bit = int(long.group(1))

            if bit is None:
                raise CircuitParseError(f"Output inválido em q{q}: {cell}")

            if circuit.cbits and f"c{bit}" not in circuit.cbits:
                raise CircuitValidationError(
                    f"Medição usa c{bit}, mas os bits declarados são {circuit.cbits}."
                )

            max_bit = max(max_bit, bit)
            outputs.append(Operation("measure", qubits=(q,), clbits=(bit,)))

        return outputs, max_bit + 1 if max_bit >= 0 else 0

    def _parse_layers(self, circuit: QC) -> list[Layer]:
        if circuit.io:
            time_indexes = range(1, len(circuit.matrix[0]) - 1)
        else:
            time_indexes = range(len(circuit.matrix[0]))

        return [
            self._parse_layer([(row, circuit.matrix[row][col]) for row in range(len(circuit.matrix))], circuit.gates)
            for col in time_indexes
        ]

    def _parse_layer(self, cells: list[tuple[int, Any]], gates: Gates) -> Layer:
        layer = Layer()
        controls: dict[str, tuple[str, int]] = {}
        targets: dict[str, tuple[str, int]] = {}
        blocks: dict[int, dict[str, Any]] = {}
        observations: dict[str, list[int]] = {}
        separators: list[str] = []

        for q, cell in cells:
            if cell in self.EMPTY:
                continue

            if isinstance(cell, QC):
                ref = id(cell)
                blocks.setdefault(ref, {"circuit": cell, "qubits": []})
                blocks[ref]["qubits"].append(q)
                continue

            if isinstance(cell, Control):
                controls[cell.id] = (cell.gate.upper(), q)
                continue

            if isinstance(cell, Target):
                targets[cell.id] = (cell.gate.upper(), q)
                continue

            if isinstance(cell, Observe):
                observations.setdefault(cell.name, []).append(q)
                continue

            if isinstance(cell, Separator):
                separators.append(cell.name)
                continue

            if isinstance(cell, str):
                token = cell.strip()
                if token in self.EMPTY:
                    continue
                if token.upper() in {"BAR", "BARRIER"}:
                    separators.append("barrier")
                    continue
                if token.upper().startswith("OBS:"):
                    observations.setdefault(token.split(":", 1)[1], []).append(q)
                    continue
                if token.upper().startswith("SEP"):
                    separators.append(token)
                    continue

                gate_name = token.upper()
                if gates.has(gate_name):
                    gate = gates.get(gate_name)
                    if gate.arity != 1:
                        raise CircuitParseError(
                            f"Porta {gate.name} tem aridade {gate.arity}. "
                            f"Use subcircuito direto na matriz para portas multiqubit."
                        )
                    layer.add(Operation(
                        gate.kind,
                        qubits=(q,),
                        params={"gate": gate.name, **gate.params},
                        label=gate.label,
                    ))
                    continue

            raise CircuitParseError(f"Célula não reconhecida em q{q}: {cell}")

        for op in self._resolve_controlled(controls, targets):
            layer.add(op)
        for op in self._resolve_blocks(blocks):
            layer.add(op)
        for name, qubits in observations.items():
            layer.add(Operation("observe", qubits=tuple(sorted(qubits)), params={"name": name, "collapse": False}, label=f"OBS({name})"))
        for name in dict.fromkeys(separators):
            layer.add(Operation("separator", qubits=(), params={"name": name}, label=str(name)))

        return layer

    def _resolve_controlled(self, controls, targets) -> list[Operation]:
        operations = []
        for id_ in sorted(set(controls) | set(targets)):
            if id_ not in controls:
                raise CircuitParseError(f"Controle ausente para operação {id_}.")
            if id_ not in targets:
                raise CircuitParseError(f"Alvo ausente para operação {id_}.")

            c_gate, c_q = controls[id_]
            t_gate, t_q = targets[id_]
            if c_gate != t_gate:
                raise CircuitParseError(f"Operação {id_} mistura {c_gate} e {t_gate}.")
            if c_gate != "CX":
                raise CircuitParseError(f"Porta controlada ainda não suportada: {c_gate}")

            operations.append(Operation(
                "cx",
                qubits=(c_q, t_q),
                params={"id": id_, "control": c_q, "target": t_q},
                label=f"CX({id_})",
            ))
        return operations

    def _resolve_blocks(self, blocks: dict[int, dict[str, Any]]) -> list[Operation]:
        operations = []
        for data in blocks.values():
            subcircuit = data["circuit"]
            used_qubits = tuple(sorted(data["qubits"]))
            sub_ir = self.parse(subcircuit)

            if sub_ir.n_qubits != len(used_qubits):
                raise CircuitValidationError(
                    f"Subcircuito {subcircuit.name} tem {sub_ir.n_qubits} qubits, "
                    f"mas foi aplicado em {len(used_qubits)} linhas."
                )
            if sub_ir.outputs:
                raise CircuitValidationError(
                    f"Subcircuito {subcircuit.name} tem medição interna. "
                    f"Subcircuito usado como bloco unitário não deve medir."
                )

            operations.append(Operation(
                "block",
                qubits=used_qubits,
                params={"circuit": sub_ir},
                label=subcircuit.name,
            ))
        return operations


# ============================================================
# Exportador para Qiskit
# ============================================================

class QiskitExporter:
    def export(self, ir: CircuitIR):
        from qiskit import QuantumCircuit

        qc = QuantumCircuit(ir.n_qubits, ir.n_clbits)

        for state in ir.inputs:
            if state.kind == "ket" and state.value == "1":
                qc.x(state.qubits[0])
            elif state.kind == "ket" and state.value == "0":
                pass
            else:
                raise CircuitValidationError(
                    f"Estado {state.kind}({state.value}) ainda não possui exportação direta para Qiskit."
                )

        for layer in ir.layers:
            for op in layer.operations:
                self._apply(qc, op)

        for op in ir.outputs:
            qc.measure(op.qubits[0], op.clbits[0])

        return qc

    def _apply(self, qc, op: Operation):
        if op.kind in {"h", "x", "y", "z", "s", "t"}:
            getattr(qc, op.kind)(op.qubits[0])
            return

        if op.kind in {"rx", "ry", "rz", "p"}:
            getattr(qc, op.kind)(op.params["theta"], op.qubits[0])
            return

        if op.kind == "cx":
            qc.cx(op.params["control"], op.params["target"])
            return

        if op.kind == "cz":
            qc.cz(op.params["control"], op.params["target"])
            return

        if op.kind == "cp":
            qc.cp(op.params["theta"], op.params["control"], op.params["target"])
            return

        if op.kind == "swap":
            qc.swap(op.params["left"], op.params["right"])
            return

        if op.kind == "mcx":
            qc.mcx(list(op.params["controls"]), op.params["target"])
            return

        if op.kind == "ccx":
            qc.ccx(*op.qubits)
            return

        if op.kind == "measure":
            qc.measure(op.qubits[0], op.clbits[0])
            return

        if op.kind == "barrier":
            qc.barrier()
            return

        if op.kind == "initialize":
            qc.initialize(list(op.params["amplitudes"]), list(op.qubits))
            return

        if op.kind == "unitary":
            qc.unitary(op.params["matrix"], list(op.qubits), label=op.label)
            return

        if op.kind == "block":
            sub_qc = self.export(op.params["circuit"])
            gate = sub_qc.to_gate(label=op.label or op.params["circuit"].name)
            qc.compose(gate, list(op.qubits), inplace=True)
            return

        if op.kind == "separator":
            qc.barrier()
            return

        if op.kind == "observe":
            # Marco lógico sem colapso: vira uma caixa vazia rotulada no desenho.
            from qiskit import QuantumCircuit
            label = op.label or f"OBS({op.params.get('name', 'obs')})"
            marker = QuantumCircuit(len(op.qubits), name=label).to_gate(label=label)
            qc.compose(marker, list(op.qubits), inplace=True)
            return

        if "qiskit_gate" in op.params:
            qc.append(op.params["qiskit_gate"], list(op.qubits))
            return

        if "matrix" in op.params:
            from qiskit.circuit.library import UnitaryGate
            gate = UnitaryGate(op.params["matrix"], label=op.label)
            qc.append(gate, list(op.qubits))
            return

        # Porta customizada sem matriz: preserva o desenho como caixa identidade.
        from qiskit import QuantumCircuit
        label = op.label or op.kind.upper()
        marker = QuantumCircuit(len(op.qubits), name=label).to_gate(label=label)
        qc.compose(marker, list(op.qubits), inplace=True)


# ============================================================
# Descrição textual da IR
# ============================================================

def describe(ir: CircuitIR) -> str:
    lines = [
        f"CircuitIR: {ir.name}",
        f"qubits={ir.n_qubits}, clbits={ir.n_clbits}",
        "",
        "INPUTS:",
    ]

    lines += [
        f"  q{state.qubits[0]} = |{state.value}>" if state.kind == "ket"
        else f"  q{state.qubits} = {state.value}"
        for state in ir.inputs
    ] or ["  -"]

    lines.append("")
    lines.append("LAYERS:")

    for i, layer in enumerate(ir.layers):
        ops = []
        for op in layer.operations:
            if op.kind == "block":
                ops.append(f"{op.label} q={op.qubits}")
            elif op.kind == "observe":
                ops.append(f"OBS({op.params['name']}) q={op.qubits}")
            elif op.kind == "separator":
                ops.append(f"SEP({op.params['name']})")
            elif op.kind == "measure":
                ops.append(f"M q={op.qubits}->c{op.clbits}")
            else:
                ops.append(f"{op.kind.upper()} q={op.qubits}")
        lines.append(f"  t{i}: " + (" | ".join(ops) if ops else "-"))

    lines.append("")
    lines.append("OUTPUTS:")
    lines += [f"  q{op.qubits[0]} -> c{op.clbits[0]}" for op in ir.outputs] or ["  -"]

    return "\n".join(lines)


# ============================================================
# Ponte simples para a pipeline
# ============================================================
# Mantém a arquitetura original QC -> Adapter -> Exporter,
# mas esconde esse caminho na API pública do notebook.
