# quantum-cq

A Python toolkit for quantum data encoding, navigation encoders, circuit
generation, metrics and experiments with Qiskit.

`quantum-cq` exposes a high-level `CQ` facade for building quantum circuits from
classical data, exporting them to Qiskit, inspecting structural metrics and
running small experiment matrices. It is intended for education, prototyping and
research-oriented engineering around data encoding, reversible query oracles and
compact circuit descriptions.

The package includes classical state encoders such as basis, angle, phase and
feature-map style encodings. It also includes a navigation encoder for addressed
classical memory, where a reversible query circuit implements the logical
semantics:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

When the data register starts at zero, this behaves as:

```text
U_D |a>|0> = |a>|D[a]>
```

The project is experimental and Qiskit-focused. It does not claim quantum
advantage, scalable QRAM hardware or physical QRAM construction.

## Installation

Base install:

```bash
pip install quantum-cq
```

Optional extras:

```bash
pip install "quantum-cq[aer]"       # local simulation with qiskit-aer
pip install "quantum-cq[ibm]"       # IBM Quantum Runtime integration
pip install "quantum-cq[notebook]"  # pandas, matplotlib, pylatexenc, IPython, widgets
pip install "quantum-cq[all]"       # all optional runtime and notebook extras
```

Dependency groups:

| Install | Includes | Use when |
| --- | --- | --- |
| `quantum-cq` | `qiskit`, `numpy`, `packaging` | Build and export circuits. |
| `quantum-cq[aer]` | `qiskit-aer` | Run local ideal/noisy simulation paths that need Aer. |
| `quantum-cq[ibm]` | `qiskit-ibm-runtime` | Submit jobs through IBM Quantum Runtime. |
| `quantum-cq[notebook]` | `pandas`, `matplotlib`, `pylatexenc`, `ipython`, `ipywidgets` | Rich display in notebooks and dataframes. |
| `quantum-cq[all]` | all optional extras | Development notebooks or full local experimentation. |

More detail:
https://github.com/jyrikes/quantum-cq/blob/main/docs/installation.md

## Quickstart

```python
from quantum_cq import CQ

data = [0, 1, 1, 0]
encoded = CQ.state(data, encoding="basis")

qc = CQ.to_qiskit(encoded)
print(qc.num_qubits, qc.depth())
print(CQ.metrics(encoded))
```

`CQ.state(..., encoding="basis")` prepares one qubit per bit and applies `X` to
qubits whose input value is `1`.

## State Encoding Examples

Automatic selection:

```python
from quantum_cq import CQ

basis_state = CQ.encode([1, 0, 1])
angle_state = CQ.encode([0.1, 0.2, 0.3])

print(basis_state.encoding_name)  # basis
print(angle_state.encoding_name)  # angle
```

Manual encoding:

```python
from quantum_cq import CQ

angle = CQ.state([0.1, 0.2, 0.3], encoding="angle")
phase = CQ.state([0.1, 0.2, 0.3], encoding="phase")
amplitude = CQ.state([1, 0, 0, 0], encoding="amplitude")

for encoded in (angle, phase, amplitude):
    print(encoded.encoding_name, CQ.metrics(encoded))
```

Feature-map style encodings:

```python
from quantum_cq import CQ

z_map = CQ.state([0.1, 0.2], encoding="z_feature_map")
zz_map = CQ.state([0.1, 0.2], encoding="zz_feature_map")
iqp = CQ.state([0.1, 0.2], encoding="iqp")

print(CQ.metrics(z_map))
print(CQ.metrics(zz_map))
print(CQ.metrics(iqp))
```

## Navigation Encoder

```python
from quantum_cq import CQ

memory = CQ.memory([3, 5, 7, 9])
nav = CQ.nav(memory, engine="explicit")

qc = CQ.to_qiskit(nav)
print(qc.num_qubits, qc.depth())
print(CQ.metrics(nav))
```

This memory means:

```text
D[0] = 3
D[1] = 5
D[2] = 7
D[3] = 9
```

The navigation circuit implements:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

With `b = 0`, this gives:

```text
U_D |a>|0> = |a>|D[a]>
```

Address bits and data bits are interpreted as little-endian integers in the
current implementation. See:
https://github.com/jyrikes/quantum-cq/blob/main/docs/navigation_encoder.md

## Why Navigation Encoding?

Traditional state encoders prepare quantum states from classical data. Some
algorithms and experiments need a different primitive: coherent access to a
classical function or table by address.

In a quantum circuit, a classical function must be embedded reversibly. The
common oracle form is:

```text
U_f |x>|y> = |x>|y xor f(x)>
```

`quantum-cq` applies the same idea to addressed memory:

```text
U_D |a>|b> = |a>|b xor D[a]>
```

This is useful for studying reversible data access, query-oracle construction,
graph navigation and quantum-walk style prototypes without claiming physical
QRAM or speedup.

## QRAM-like Semantics, Not Physical QRAM

The `qram_like` engine simulates the logical query semantics of an addressed
quantum memory. It does not implement a physical QRAM architecture and should
not be interpreted as evidence of scalable QRAM hardware.

In Portuguese: `engine="qram_like"` simula a semantica logica de consulta
enderecada, mas nao e uma QRAM fisica e nao implica vantagem quantica.

## Graph Navigation And Quantum Walk MVP

Graph navigation encodes neighbor lookup semantics. Padding directions use
self-loop behavior by default.

```python
from quantum_cq import CQ

graph = CQ.graph(edges=[(0, 1), (1, 2), (2, 3)], vertices=4)
neighbor_oracle = CQ.graph_nav(graph, engine="explicit")

print(CQ.metrics(neighbor_oracle))
```

A small coined-walk primitive can be built for small graphs and inspected as a
unitary circuit:

```python
from quantum_cq import CQ

cycle = CQ.graph(edges=[(0, 1), (1, 2), (2, 3), (3, 0)], vertices=4)
walk_step = CQ.walk(cycle, steps=1)

print(CQ.metrics(walk_step))
```

The walk support is an MVP for small-graph operator construction. It does not
claim search speedup or continuous-time/Szegedy walk coverage.

## Algorithms, Operators And Primitives

Algorithm builders return `AlgorithmCircuit` objects:

```python
from quantum_cq import CQ

deutsch = CQ.deutsch(case=2)
bv = CQ.bv("1011")
dj = CQ.dj(kind="balanced", qubits=3)
grover = CQ.grover("11")
qpe = CQ.qpe(phase=0.25, precision=3)

for circuit in (deutsch, bv, dj, grover, qpe):
    print(circuit.algorithm_name, CQ.metrics(circuit))
```

Reusable operators and primitives:

```python
from quantum_cq import CQ

qft = CQ.qft(3)
iqft = CQ.iqft(3)
diffuser = CQ.diffuser(3)
phase_rotation = CQ.phase_rotation(0.25)

print(CQ.metrics(qft))
print(CQ.metrics(phase_rotation))
```

These tools are intended for circuit construction and inspection. They are not
a replacement for a full algorithm library.

## QC Compact Circuit DSL

The compact `QC` table DSL remains supported and can be exported through the
same facade.

```python
from quantum_cq import CQ
from quantum_cq.algorithms import twobit_block
from quantum_cq.compact import QC, m, obs, sep

uf = twobit_block(2)
qc = QC(
    "Deutsch",
    [
        [0, "-", "H", obs("pre_oracle"), uf, sep("after_oracle"), "H", m(0)],
        [0, "X", "H", obs("pre_oracle"), uf, "-", "-", "-"],
    ],
    c=1,
)

assert CQ.from_qc(qc) is qc
qiskit_circuit = CQ.to_qiskit(qc)
print(qiskit_circuit.num_qubits, qiskit_circuit.depth())
```

## Metrics

`CQ.metrics(...)` accepts raw Qiskit circuits and quantum-cq result wrappers.
It reports structural circuit information and preserves relevant metadata.

```python
from quantum_cq import CQ

encoded = CQ.state([1, 0, 1], encoding="basis")
metrics = CQ.metrics(encoded)

print(metrics["num_qubits"])
print(metrics["depth"])
print(metrics["count_ops"])
```

Currently collected metrics include:

- number of qubits and classical bits;
- circuit depth and size;
- operation counts;
- `cx`, `mcx`, `swap`, `cp` and measurement counts;
- two-qubit gate count for `cx`, `cz`, `cp` and `swap`;
- metadata such as encoding name, algorithm name, navigation engine and QRAM caveats.

Experiment pipelines may also include counts and per-experiment metadata in
their result objects.

## Experiment Pipeline

`CQ.run(...)` expands small experiment matrices over circuits, data, encoders
and modes.

```python
from quantum_cq import CQ

result = CQ.run(
    data=[0.1, 0.2, 0.3],
    encoders=["angle", "phase"],
    modes=["ideal"],
    shots=128,
)

print(result.summary())
print(result.global_metrics())
```

Local ideal/noisy modes may require `quantum-cq[aer]`. IBM Runtime execution
requires `quantum-cq[ibm]` and user-managed credentials.

## API Overview

```python
from quantum_cq import CQ

state = CQ.state([1, 0, 1], encoding="basis")
auto_state = CQ.encode([0.1, 0.2])

memory = CQ.memory([3, 5, 7, 9])
navigation = CQ.nav(memory, engine="explicit")

qiskit_circuit = CQ.to_qiskit(navigation)
metrics = CQ.metrics(navigation)

pipeline_result = CQ.run(data=[0.1, 0.2], encoder="angle", mode="ideal", shots=64)
```

More examples:
https://github.com/jyrikes/quantum-cq/blob/main/docs/api_overview.md

## Supported Encodings

| Encoding | Purpose | Notes |
| --- | --- | --- |
| `basis` | Binary data to computational-basis state. | Auto-selected for pure binary integer sequences. |
| `angle` | Numeric data to `ry` rotations. | Auto-selected for non-binary numeric sequences. |
| `dense_angle` | More than one feature per qubit. | Manual selection. |
| `phase` | Numeric data to phase gates. | Manual selection. |
| `amplitude` | Numeric vector to amplitudes. | Input length must be a power of two. |
| `z_feature_map` | Z-phase feature map. | Manual feature-map encoding. |
| `zz_feature_map` | Pairwise ZZ interaction feature map. | Encodes simple feature interactions. |
| `pauli_feature_map` | Pauli feature-map style circuit. | Supports configured Pauli terms. |
| `iqp` | IQP-style feature map. | H-diagonal-H structure. |
| `data_reuploading` | Repeated data-uploading layers. | Repetition count comes from metadata. |

## Navigation Engines

| Engine | Description | Caveat |
| --- | --- | --- |
| `explicit` | Builds an explicit reversible XOR-load circuit. | Cost scales with address space and data width. |
| `sparse` | Skips zero-valued entries when possible. | Still an explicit circuit construction. |
| `qram_like` | Uses logical addressed-query metadata and delegates to an explicit/sparse engine. | Not physical QRAM; no hardware speedup claim. |

Aliases accepted by `CQ.nav(...)` include `explicit`, `sparse`, `qram`,
`qram_like` and `oracle`. The `oracle` model is planned and raises
`NotImplementedError` for concrete builds.

## Features

- High-level `CQ` facade.
- Classical state encoders.
- Navigation encoder for addressed memory.
- Graph navigation and small quantum-walk MVP.
- Qiskit circuit export.
- Structural circuit metrics.
- Runtime abstraction and experiment pipeline.
- Optional Aer, IBM Runtime and notebook integrations.

## Example Scripts

Run from a checkout:

```bash
PYTHONPATH=src python examples/basic_state_encoding.py
PYTHONPATH=src python examples/basic_navigation.py
```

Or after installation:

```bash
python examples/basic_state_encoding.py
python examples/basic_navigation.py
```

## Project Status

`quantum-cq` is an early research-oriented package. The public API is centered
on the `CQ` facade and may evolve, but the `0.1.x` series aims to preserve the
documented examples.

## Safety Notes

- Do not commit service tokens, PyPI tokens or IBM Runtime credentials.
- `qram_like` means logical query semantics only.
- The package is a toolkit for circuit construction and experiments, not a
claim of quantum advantage.
