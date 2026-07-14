"""Deterministic parser and lowering for the initial MQT equation grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quantum_cq._circuits.compact import CircuitIR, Layer, LogicalCircuitBuilder, Operation
from quantum_cq._circuits.unitary import CustomUnitary, unitary_payload
from quantum_cq._runtime.unified import basis_inputs, operation_for_gate, parse_clbit_token, parse_qubit_token


class MQTParseError(ValueError):
    pass


class MQTSemanticError(ValueError):
    pass


@dataclass(frozen=True)
class SourceSpan:
    line: int
    column: int
    text: str


@dataclass(frozen=True)
class MQTDiagnostic:
    message: str
    line: int
    column: int
    level: str = "error"


@dataclass(frozen=True)
class ExprNode:
    kind: str
    value: Any = None
    children: tuple["ExprNode", ...] = ()
    qubits: tuple[int, ...] = ()
    params: tuple[Any, ...] = ()
    span: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "children", tuple(self.children))
        object.__setattr__(self, "qubits", tuple(self.qubits))
        object.__setattr__(self, "params", tuple(self.params))


@dataclass(frozen=True)
class MQTAssignment:
    target: str
    expression: ExprNode
    span: SourceSpan


@dataclass(frozen=True)
class MQTMeasurement:
    basis: str
    qubits: tuple[int, ...]
    clbits: tuple[int, ...]
    span: SourceSpan

    def __post_init__(self) -> None:
        object.__setattr__(self, "qubits", tuple(self.qubits))
        object.__setattr__(self, "clbits", tuple(self.clbits))


@dataclass(frozen=True)
class MQTProgram:
    source: str
    assignment: MQTAssignment
    measurements: tuple[MQTMeasurement, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "measurements", tuple(self.measurements))


@dataclass(frozen=True)
class ResolvedSymbol:
    name: str
    category: str
    arity: int
    parameters: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    lowering: str | None = None
    provenance: str = "builtin"
    value: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "requirements", tuple(self.requirements))


@dataclass(frozen=True)
class SemanticOperation:
    symbol: ResolvedSymbol
    qubits: tuple[int, ...]
    params: tuple[Any, ...] = ()
    adjoint: bool = False
    source: SourceSpan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "qubits", tuple(self.qubits))
        object.__setattr__(self, "params", tuple(self.params))


@dataclass(frozen=True)
class SemanticProgram:
    source: str
    state_label: str
    basis: str
    n_qubits: int
    operations: tuple[SemanticOperation, ...]
    measurements: tuple[MQTMeasurement, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    requirements: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "measurements", tuple(self.measurements))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "requirements", tuple(self.requirements))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


BUILTIN_GATES: dict[str, ResolvedSymbol] = {
    "I": ResolvedSymbol("I", "gate", 1, lowering="identity"),
    "H": ResolvedSymbol("H", "gate", 1, lowering="h"),
    "X": ResolvedSymbol("X", "gate", 1, lowering="x"),
    "Y": ResolvedSymbol("Y", "gate", 1, lowering="y"),
    "Z": ResolvedSymbol("Z", "gate", 1, lowering="z"),
    "S": ResolvedSymbol("S", "gate", 1, lowering="s"),
    "T": ResolvedSymbol("T", "gate", 1, lowering="t"),
    "RX": ResolvedSymbol("RX", "gate", 1, parameters=("theta",), lowering="rx"),
    "RY": ResolvedSymbol("RY", "gate", 1, parameters=("theta",), lowering="ry"),
    "RZ": ResolvedSymbol("RZ", "gate", 1, parameters=("theta",), lowering="rz"),
    "P": ResolvedSymbol("P", "gate", 1, parameters=("theta",), lowering="p"),
    "CX": ResolvedSymbol("CX", "gate", 2, lowering="cx"),
    "CZ": ResolvedSymbol("CZ", "gate", 2, lowering="cz"),
    "CP": ResolvedSymbol("CP", "gate", 2, parameters=("theta",), lowering="cp"),
    "SWAP": ResolvedSymbol("SWAP", "gate", 2, lowering="swap"),
}
RESERVED = set(BUILTIN_GATES) | {"MEASURE", "TENSOR", "DAGGER", "PI"}


def parse_equation(source: str) -> MQTProgram:
    _reject_unsafe_source(source)
    lines = [
        (line_no, raw.strip())
        for line_no, raw in enumerate(source.splitlines(), start=1)
        if raw.strip()
    ]
    assignments = [(line_no, line) for line_no, line in lines if ":=" in _normalize_aliases(line)]
    if len(assignments) != 1:
        raise MQTParseError("MQT requer exatamente uma atribuicao principal")

    assignment_line_no, assignment_line = assignments[0]
    normalized = _normalize_aliases(assignment_line)
    left, right = normalized.split(":=", 1)
    target = _parse_state_label(left.strip(), assignment_line_no)
    assignment = MQTAssignment(
        target=target,
        expression=_parse_expr(right.strip(), assignment_line_no, assignment_line.find(":=") + 3),
        span=SourceSpan(assignment_line_no, 1, assignment_line),
    )
    measurements = []
    for line_no, line in lines:
        if line_no == assignment_line_no:
            continue
        normalized_line = _normalize_aliases(line)
        if normalized_line.lower().startswith("measure "):
            measurements.append(_parse_measurement(normalized_line, line_no, line))
            continue
        if ":=" in normalized_line:
            raise MQTParseError("Multiplas atribuicoes nao sao suportadas nesta run")
        raise MQTParseError(f"Estrutura MQT fora do escopo na linha {line_no}: {line}")
    return MQTProgram(source=source, assignment=assignment, measurements=tuple(measurements))


def semantic_program(
    program: MQTProgram,
    *,
    parameters: dict[str, Any] | None = None,
    symbols: dict[str, Any] | None = None,
) -> SemanticProgram:
    parameters = dict(parameters or {})
    symbols = dict(symbols or {})
    _check_symbol_conflicts(parameters, symbols)
    terms = _composition_terms(program.assignment.expression)
    if not terms:
        raise MQTSemanticError("Expressao MQT vazia")
    basis = _basis_from_expr(terms[-1])
    n_qubits = len(basis)
    operations: list[SemanticOperation] = []
    for term in reversed(terms[:-1]):
        operations.extend(_semantic_operations(term, n_qubits, parameters, symbols))
    for measurement in program.measurements:
        _validate_measurement(measurement, n_qubits)
    requirements = tuple(sorted({op.symbol.lowering or op.symbol.name.lower() for op in operations if op.symbol.name != "I"}))
    return SemanticProgram(
        source=program.source,
        state_label=program.assignment.target,
        basis=basis,
        n_qubits=n_qubits,
        operations=tuple(operations),
        measurements=program.measurements,
        parameters=parameters,
        requirements=requirements,
        provenance={"grammar": "run4.mqt.v1"},
    )


def lower_to_circuit(program: SemanticProgram) -> CircuitIR:
    layers: list[Layer] = []
    for semantic in program.operations:
        if semantic.symbol.name == "I":
            continue
        op = _lower_operation(semantic)
        layer = Layer()
        layer.add(op)
        layers.append(layer)
    outputs = [
        Operation("measure", qubits=(qubit,), clbits=(clbit,))
        for measurement in program.measurements
        for qubit, clbit in zip(measurement.qubits, measurement.clbits, strict=True)
    ]
    n_clbits = max((clbit for measurement in program.measurements for clbit in measurement.clbits), default=-1) + 1
    return CircuitIR(
        name=program.state_label,
        n_qubits=program.n_qubits,
        n_clbits=max(n_clbits, 0),
        inputs=basis_inputs(program.basis),
        layers=layers,
        outputs=outputs,
        metadata={
            "source": "mqt",
            "semantic_ir": "run4.mqt.v1",
            "requirements": program.requirements,
        },
    )


def _parse_expr(text: str, line: int, column: int) -> ExprNode:
    text = _strip_wrapping_parens(text.strip())
    parts = _split_top_level(text, "\u00b7")
    if len(parts) > 1:
        return ExprNode(
            "compose",
            children=tuple(_parse_expr(part, line, column + text.find(part)) for part in parts),
            span=SourceSpan(line, column, text),
        )
    parts = _split_top_level(text, "\u2297")
    if len(parts) > 1:
        return ExprNode(
            "tensor",
            children=tuple(_parse_expr(part, line, column + text.find(part)) for part in parts),
            span=SourceSpan(line, column, text),
        )
    if text.endswith("\u2020"):
        child = _parse_expr(text[:-1], line, column)
        return ExprNode("adjoint", children=(child,), span=SourceSpan(line, column, text))
    if _is_ket(text):
        return ExprNode("ket", value=_ket_bits(text), span=SourceSpan(line, column, text))
    call = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\(([^()]*)\))?\[([^][]*)\]", text)
    if call:
        name = call.group(1)
        params = tuple(item.strip() for item in (call.group(2) or "").split(",") if item.strip())
        qubits = tuple(parse_qubit_token(item.strip()) for item in call.group(3).split(",") if item.strip())
        return ExprNode("operator", value=name, params=params, qubits=qubits, span=SourceSpan(line, column, text))
    raise MQTParseError(f"Expressao MQT invalida na linha {line}, coluna {column}: {text}")


def _parse_measurement(normalized: str, line_no: int, original: str) -> MQTMeasurement:
    match = re.fullmatch(r"measure\s+([A-Za-z]+)\[([^][]*)\]\s*->\s*c\[([^][]*)\]", normalized)
    if not match:
        match = re.fullmatch(r"measure\s+([qQ]\d+)\s*->\s*([cC]\d+)", normalized)
        if not match:
            raise MQTParseError(f"Medicao invalida na linha {line_no}: {original}")
        qubits = (parse_qubit_token(match.group(1).lower()),)
        clbits = (parse_clbit_token(match.group(2).lower()),)
        return MQTMeasurement("Z", qubits, clbits, SourceSpan(line_no, 1, original))
    qubits = tuple(parse_qubit_token(item.strip()) for item in match.group(2).split(",") if item.strip())
    clbits = tuple(parse_clbit_token(item.strip()) for item in match.group(3).split(",") if item.strip())
    return MQTMeasurement(match.group(1).upper(), qubits, clbits, SourceSpan(line_no, 1, original))


def _semantic_operations(
    expr: ExprNode,
    n_qubits: int,
    parameters: dict[str, Any],
    symbols: dict[str, Any],
    *,
    adjoint: bool = False,
) -> list[SemanticOperation]:
    if expr.kind == "tensor":
        ops: list[SemanticOperation] = []
        for child in expr.children:
            ops.extend(_semantic_operations(child, n_qubits, parameters, symbols, adjoint=adjoint))
        return ops
    if expr.kind == "adjoint":
        return _semantic_operations(expr.children[0], n_qubits, parameters, symbols, adjoint=not adjoint)
    if expr.kind != "operator":
        raise MQTSemanticError("Somente operadores podem aparecer antes do estado base")
    symbol = _resolve_symbol(str(expr.value), symbols)
    if len(expr.qubits) != symbol.arity:
        raise MQTSemanticError(f"Simbolo {symbol.name} requer {symbol.arity} qubit(s), recebeu {len(expr.qubits)}")
    if len(set(expr.qubits)) != len(expr.qubits):
        raise MQTSemanticError(f"Simbolo {symbol.name} recebeu qubits repetidos")
    if any(qubit < 0 or qubit >= n_qubits for qubit in expr.qubits):
        raise MQTSemanticError(f"Simbolo {symbol.name} usa qubit fora da dimensao do estado")
    params = tuple(_resolve_param(item, parameters, expr) for item in expr.params)
    if len(params) != len(symbol.parameters):
        if symbol.parameters:
            raise MQTSemanticError(f"Simbolo {symbol.name} requer parametro(s) {symbol.parameters}")
    return [SemanticOperation(symbol, expr.qubits, params, adjoint=adjoint, source=expr.span)]


def _resolve_symbol(name: str, symbols: dict[str, Any]) -> ResolvedSymbol:
    key = name.upper()
    if key in BUILTIN_GATES:
        return BUILTIN_GATES[key]
    if name in symbols:
        value = symbols[name]
    elif key in symbols:
        value = symbols[key]
    else:
        raise MQTSemanticError(f"Simbolo desconhecido: {name}")
    arity = _symbol_arity(value)
    category = "circuit" if _looks_like_circuit_symbol(value) else "unitary"
    return ResolvedSymbol(
        name=name,
        category=category,
        arity=arity,
        requirements=("unitary" if category == "unitary" else "block",),
        lowering=category,
        provenance="symbols",
        value=value,
    )


def _lower_operation(semantic: SemanticOperation) -> Operation:
    symbol = semantic.symbol
    if symbol.category == "gate":
        params = {}
        if semantic.params:
            params["theta"] = semantic.params[0]
        if semantic.adjoint and symbol.name not in {"S", "T"}:
            raise MQTSemanticError(f"Adjunto nao suportado para {symbol.name} nesta run")
        if semantic.adjoint and symbol.name == "S":
            return Operation("p", qubits=semantic.qubits, params={"theta": -1.5707963267948966})
        if semantic.adjoint and symbol.name == "T":
            return Operation("p", qubits=semantic.qubits, params={"theta": -0.7853981633974483})
        return operation_for_gate(symbol.name, semantic.qubits, params)
    if symbol.category == "unitary":
        payload = unitary_payload(symbol.value, semantic.qubits, name=symbol.name)
        return Operation("unitary", qubits=semantic.qubits, params=payload, label=symbol.name)
    if symbol.category == "circuit":
        circuit = symbol.value.build() if isinstance(symbol.value, LogicalCircuitBuilder) else symbol.value
        return Operation("block", qubits=semantic.qubits, params={"circuit": circuit}, label=symbol.name)
    raise MQTSemanticError(f"Lowering nao suportado para {symbol.name}")


def _composition_terms(expr: ExprNode) -> tuple[ExprNode, ...]:
    return expr.children if expr.kind == "compose" else (expr,)


def _basis_from_expr(expr: ExprNode) -> str:
    if expr.kind != "ket":
        raise MQTSemanticError("Expressao MQT deve terminar em basis ket")
    bits = str(expr.value)
    if not bits or set(bits) - {"0", "1"}:
        raise MQTSemanticError("Basis ket deve conter somente 0 e 1")
    return bits


def _validate_measurement(measurement: MQTMeasurement, n_qubits: int) -> None:
    if measurement.basis != "Z":
        raise MQTSemanticError("Somente medicao Z e suportada nesta run")
    if len(measurement.qubits) != len(measurement.clbits):
        raise MQTSemanticError("Medicao requer mesma quantidade de qubits e clbits")
    if len(set(measurement.qubits)) != len(measurement.qubits):
        raise MQTSemanticError("Medicao recebeu qubits repetidos")
    if len(set(measurement.clbits)) != len(measurement.clbits):
        raise MQTSemanticError("Medicao recebeu clbits repetidos")
    if any(qubit < 0 or qubit >= n_qubits for qubit in measurement.qubits):
        raise MQTSemanticError("Medicao usa qubit fora da dimensao do estado")


def _symbol_arity(value: Any) -> int:
    if isinstance(value, CustomUnitary):
        return value.num_qubits
    if isinstance(value, LogicalCircuitBuilder):
        return value.build().n_qubits
    if isinstance(value, CircuitIR):
        return value.n_qubits
    if hasattr(value, "num_qubits"):
        return int(value.num_qubits)
    raise MQTSemanticError(f"Simbolo externo sem aridade conhecida: {value!r}")


def _looks_like_circuit_symbol(value: Any) -> bool:
    return isinstance(value, (LogicalCircuitBuilder, CircuitIR)) or hasattr(value, "layers")


def _resolve_param(token: str, parameters: dict[str, Any], expr: ExprNode) -> Any:
    normalized = token.strip()
    aliases = {"\u03b8": "theta", "\u03c6": "phi"}
    normalized = aliases.get(normalized, normalized)
    lowered = normalized.lower()
    if lowered == "pi":
        return 3.141592653589793
    if normalized in parameters:
        return parameters[normalized]
    try:
        return float(normalized)
    except ValueError:
        span = expr.span or SourceSpan(1, 1, normalized)
        raise MQTSemanticError(f"Parametro desconhecido {normalized} na linha {span.line}, coluna {span.column}") from None


def _check_symbol_conflicts(parameters: dict[str, Any], symbols: dict[str, Any]) -> None:
    for source_name, mapping in (("parameters", parameters), ("symbols", symbols)):
        for name in mapping:
            if name.upper() in RESERVED:
                raise MQTSemanticError(f"Simbolo reservado sobrescrito por {source_name}: {name}")
    overlap = set(parameters) & set(symbols)
    if overlap:
        name = sorted(overlap)[0]
        raise MQTSemanticError(f"Conflito de simbolo {name}: parameters e symbols")


def _normalize_aliases(text: str) -> str:
    replacements = {
        "|psi>": "|\u03c8\u27e9",
        "|beta00>": "|\u03b2\u2080\u2080\u27e9",
        "|0>": "|0\u27e9",
        "|1>": "|1\u27e9",
        "tensor": "\u2297",
        "dagger": "\u2020",
        "*": "\u00b7",
        "\u2192": "->",
        "theta": "\u03b8",
        "phi": "\u03c6",
        "pi": "pi",
    }
    normalized = text
    for left, right in replacements.items():
        normalized = normalized.replace(left, right)
    normalized = re.sub(r"\|([01]+)>", lambda match: f"|{match.group(1)}\u27e9", normalized)
    return normalized


def _parse_state_label(text: str, line_no: int) -> str:
    if not (text.startswith("|") and text.endswith("\u27e9")):
        raise MQTParseError(f"Estado alvo invalido na linha {line_no}")
    label = text[1:-1].strip()
    if not label:
        raise MQTParseError(f"Estado alvo vazio na linha {line_no}")
    return label


def _is_ket(text: str) -> bool:
    return text.startswith("|") and text.endswith("\u27e9") and bool(_ket_bits(text))


def _ket_bits(text: str) -> str:
    inner = text[1:-1]
    return inner if set(inner) <= {"0", "1"} else ""


def _split_top_level(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    depth_paren = 0
    depth_bracket = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth_paren += 1
        elif char == ")":
            depth_paren -= 1
        elif char == "[":
            depth_bracket += 1
        elif char == "]":
            depth_bracket -= 1
        elif char == separator and depth_paren == 0 and depth_bracket == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    if parts:
        parts.append(text[start:].strip())
    return [part for part in parts if part]


def _strip_wrapping_parens(text: str) -> str:
    while text.startswith("(") and text.endswith(")") and _balanced(text[1:-1]):
        text = text[1:-1].strip()
    return text


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _reject_unsafe_source(source: str) -> None:
    lowered = source.lower()
    forbidden = ["import", "__", "eval", "exec", "lambda", "for ", "while ", "if ", "|>"]
    for token in forbidden:
        if token in lowered:
            raise MQTParseError(f"Estrutura fora do escopo ou insegura: {token.strip()}")
