# Navigation v1 Contract

Navigation v1 is the stable addressed-memory behavior shipped in `quantum-cq`
`0.1.x`. It remains Qiskit-exportable by default and must preserve its public
API, metadata, and bit ordering.

## Mathematical Contract

For an addressed memory `D`, address register `a`, and data register `b`, the
load oracle implements:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

Required invariants:

- the address register is unchanged;
- the data register is XOR-loaded with the addressed value;
- values outside the explicit memory length use the configured padded default;
- the operation is unitary for valid memories;
- the operation is an involution: applying it twice restores the input state;
- the same semantics apply to computational basis states and superpositions.

## Bit Ordering

The logical address and data values use little-endian integer interpretation:

- address bit `0` is the least significant address bit;
- data bit `0` is the least significant data bit;
- the integer basis index is `address + (data_value << address_qubits)`.

This contract does not freeze Qiskit display order for count strings beyond the
existing metadata and documented little-endian logical interpretation.

## Public Surface

The following APIs remain supported:

```python
from quantum_cq.navigation import AddressedMemory
from quantum_cq.navigation import AddressedMemoryEncoding
from quantum_cq.navigation import ExplicitCircuitMemoryEngine
from quantum_cq.navigation import SparseExplicitMemoryEngine
from quantum_cq.navigation import QRAMLikeMemoryEngine

CQ.memory(...)
CQ.nav(...)
CQ.addressed(...)
CQ.encode(..., role="navigation")
CQ.to_qiskit(...)
CQ.metrics(...)
```

## Engines

The current engines are:

- `explicit_circuit`;
- `sparse_explicit_circuit`;
- `qram_like`, delegated to sparse explicit construction.

`qram_like` is a logical simulation of QRAM-style access semantics. It is not a
claim of physical QRAM. It must preserve:

```text
physical_qram = False
simulates_qram_semantics = True
simulates_physical_qram = False
```

`oracle_model` remains abstract in this run and must fail explicitly instead of
returning a fake circuit.

## Frozen Metadata

Where applicable, Navigation v1 preserves the current metadata keys:

- `model`
- `engine`
- `access_semantics`
- `reversible`
- `physical_qram`
- `simulates_qram_semantics`
- `simulates_physical_qram`
- `nonzero_entries`
- `skipped_zero_entries`
- `delegated_engine`
- `address_bit_order`
- `data_bit_order`
- `address_qubits`
- `data_qubits`
- `memory_size`
- `address_space_size`
- `default_value`

## Not Frozen

The contract intentionally does not freeze:

- transpiled depth;
- exact physical gate count after transpilation;
- rendered circuit text;
- private helper names;
- SDK-specific internal representation details.
