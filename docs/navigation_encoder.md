# Navigation Encoder

The navigation encoder builds reversible query circuits for addressed classical
data. Its central operation is:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

If the data register starts at zero:

```text
U_D |a>|0> = |a>|D[a]>
```

This is the same reversible-oracle pattern used for classical functions:

```text
U_f |x>|y> = |x>|y xor f(x)>
```

## Addressed Memory

```python
from quantum_cq import CQ

memory = CQ.memory([3, 5, 7, 9])
nav = CQ.nav(memory, engine="explicit")

qc = CQ.to_qiskit(nav)
print(qc.num_qubits, qc.depth())
print(CQ.metrics(nav))
```

This memory table is:

```text
D[0] = 3
D[1] = 5
D[2] = 7
D[3] = 9
```

## Registers

For addressed memory, the circuit layout is:

```text
[address bits] + [data bits]
```

The current metadata uses:

- `address_bit_order = "little_endian_int"`
- `data_bit_order = "little_endian_int"`

That means bit 0 is the least significant bit of the integer value in each
register.

## XOR-load

The load operation XORs the selected memory value into the data register. It
does not overwrite the data register:

```text
|a>|b> -> |a>|b xor D[a]>
```

This makes the operation reversible. Applying the same XOR-load twice returns
the data register to its original value.

## Engines

| Engine | Description | Caveat |
| --- | --- | --- |
| `explicit` | Constructs an explicit reversible load circuit. | Cost scales with address space and data width. |
| `sparse` | Skips zero-valued entries where possible. | Still explicit circuit construction. |
| `qram_like` | Marks the operation as logical QRAM-like semantics and delegates to an explicit/sparse engine. | Not physical QRAM. |

`CQ.nav(..., engine="explicit")` maps to the internal `explicit_circuit`
engine. `engine="sparse"` maps to `sparse_explicit_circuit`.

## QRAM-like Caveat

The `qram_like` engine simulates the logical query semantics of an addressed
quantum memory. It does not implement a physical QRAM architecture and should
not be interpreted as evidence of scalable QRAM hardware.

Do not interpret this engine as a speedup claim. It is a convenient semantic
label and circuit-building path for experiments.

## Graph Navigation

Graph navigation uses addressed-memory semantics to encode neighbor lookup.

```python
from quantum_cq import CQ

graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], vertices=4)
neighbor_oracle = CQ.graph_nav(graph, engine="explicit")

print(CQ.metrics(neighbor_oracle))
```

For graph memory flattening, the implementation uses:

```text
flat_address = v * degree_space + k
```

The physical address-bit layout uses direction bits first and vertex bits after
that, so the direction index occupies the least significant part of the address.

## What This Is Not

The navigation encoder is not:

- a physical QRAM implementation;
- a proof of quantum advantage;
- a hardware architecture;
- a promise of scalable memory access.

It is a research and engineering tool for building reversible query circuits
and inspecting their structure in Qiskit.
