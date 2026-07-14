# Release 0.2.0

`quantum-cq` 0.2.0 consolidates the RUN 1 to RUN 4.3 work into `main`.

## Highlights

- Qiskit remains required and is still the default reference engine.
- Optional engines stay lazy: PennyLane, Cirq, Braket and CUDA-Q are not loaded
  by `import quantum_cq`.
- The public `CQ` facade now includes explicit multi-engine APIs:
  `CQ.engines()`, `CQ.engine_capabilities(...)`, `CQ.emit(...)`,
  `CQ.compile(...)` and `CQ.run_engine(...)`.
- `CQ.circuit(...)` exposes a SDK-free logical circuit builder.
- `CQ.unitary(...)` creates immutable custom unitary payloads with defensive
  matrix copies.
- `CQ.pipeline(...)` supports the legacy data/encoding flow and the enriched
  pipeline for equations, circuits and structural navigation inputs.
- The hardware abstraction layer provides SDK-free manual targets and explicit
  Qiskit topology extraction from objects supplied by the user.
- Navigation Encoding V1 remains the default addressed-memory path.
- Navigation Encoding V2 is available explicitly through `CQ.navigation_v2(...)`
  for exact finite typed structures.
- Exact finite coined quantum walk support is available through `CQ.walk(...)`.

## Compatibility

The V1 navigation APIs remain available and unchanged:

- `CQ.memory(...)`
- `CQ.nav(...)`
- `CQ.addressed(...)`
- `CQ.graph(...)`
- `CQ.graph_nav(...)`
- `CQ.walk(...)`
- `CQ.available_navigation_encodings()`

`CQ.available_exporters()` remains the legacy exporter registry and returns
`["qiskit"]`.

## New User-Facing Notebook

The maintained introductory notebook is:

```text
notebooks/quantum_cq_getting_started.ipynb
```

It walks through imports, state encodings, Qiskit export, V1 navigation,
custom logical circuits, engine APIs, the unified pipeline, manual targets and
Navigation V2.

The complete navigation pipeline walkthrough is:

```text
notebooks/quantum_cq_full_pipeline_navigation.ipynb
```

It shows input data, query circuits, pipeline stages, snapshots, native
transpilation records, measurements and V1/V2 data recovery.

The presentation-oriented theory and library demo is:

```text
notebooks/quantum_cq_teoria_biblioteca_demo.ipynb
```

It shows the same public architecture in a slide-friendly flow, including a
batch perceptron circuit, before/after transpilation snapshots, canonical
measurements, a Bernstein-Vazirani example and Navigation V2 logical-to-physical
qubit mapping.

## Limits

This release does not claim physical QRAM, quantum advantage, automatic backend
selection, remote execution, general graph canonicalization efficiency,
approximate structural encodings, CircuitIR v2 or Navigation v2 as a replacement
for V1.
