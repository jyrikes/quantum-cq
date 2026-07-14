# Run 3: CircuitService and Hardware Abstraction Layer

Run 3 starts after the Run 2 closing commit `89c7ad4`. The local notebook
`notebooks/quantum_cq_simple_api_lab.ipynb` remains outside the run commits.

## Run 2 closure

Run 2 was finalized before this branch was created. The closing work corrected:

- Qiskit native measurement extraction, including partial measurements and
  multiple classical registers.
- Canonical counts normalization based only on measured clbits.
- Measurement metadata for measured qubits, logical clbits, native positions,
  canonical order and native order.
- Compatibility priority: `supported`, `lowered`, `experimental`,
  `not_tested`, `unsupported`.
- Defensive immutability for engine DTO mappings.
- Catalog compatibility lookup without direct dependency on the concrete engine
  registry.
- Shot mismatch detection for precompiled artifacts.

The final Run 2 validation passed the main test suite, `compileall`, and build
before the Run 3 branch was created.

## Circuit layer

Run 3 adds a public SDK-free circuit creation path:

```python
builder = CQ.circuit(2, 2, name="bell")
builder.h(0)
builder.cx(0, 1)
builder.measure(0, 0)
builder.measure(1, 1)
logical = builder.build()
```

The returned builder uses the existing `CircuitIR`; no Semantic IR or Circuit IR
v2 was introduced. `CircuitService` is a read-only service that recognizes
supported public circuit-like objects, validates them, and produces:

- `CircuitDescriptor`
- `CircuitRequirements`

It does not emit, compile, execute, query providers, build circuits, compose
mutable circuits, perform placement, perform routing, or decompose unitary
operations.

`QuantumCircuit` is recognized only as a native Qiskit object. It is not
converted back to `CircuitIR` for optional engines.

The public builder validates structural invariants before operations enter the
IR: register sizes must be non-negative, qubit/clbit indices must be valid,
controlled operations must use distinct controls and targets, and custom
unitaries must be applied to unique valid qubits. Invalid circuits are rejected
at the logical boundary rather than being left for an SDK to fail later.

## Custom unitaries

`CQ.unitary(...)` creates a `CustomUnitary` object. The object is SDK-free and
stores a defensive immutable copy of the matrix.

Validation checks:

- two-dimensional matrix;
- square matrix;
- dimension equal to a power of two;
- numeric values;
- unitarity within the configured tolerance.

Custom unitaries are preserved as explicit `unitary` operations in `CircuitIR`.
Raw matrices passed through `builder.unitary(...)` use the same validation as
`CQ.unitary(...)`; there is no bypass path. The operation payload keeps one
neutral source of truth for the matrix and associated metadata. Unitaries are
not decomposed or synthesized automatically. Engines without tested support
report incompatibility through capabilities.

## Composition

Logical composition is available on the public builder. Composition accepts
logical circuit representations only:

- `CircuitIR`;
- `QC`;
- another logical builder;
- public wrappers whose `circuit_format` is `ir`.

When source and destination registers do not match exactly, explicit
`qubit_map` and `clbit_map` values are required. Composition preserves operation
order, measurements, custom unitary payloads, metadata and subcircuit origin.

Composition does not:

- convert `QuantumCircuit` to `CircuitIR`;
- invent ancillas;
- discard measurements;
- remap registers silently;
- choose mappings automatically.

## Hardware Abstraction Layer

Run 3 adds a neutral `_hardware` layer. Its domain models do not import Qiskit,
PennyLane, Cirq, Braket, CUDA-Q, devices, backend sessions, credentials or
provider-specific objects.

The concepts are intentionally separate:

- `ExecutionTargetDescriptor`: identity and discovery metadata.
- `TargetArchitecture`: relatively stable structure.
- `TargetStateSnapshot`: dynamic state observed at a point in time.
- `TargetProvenance`: source, adapter, SDK version, transformed fields, omitted
  fields, warnings and completeness.
- `ExecutionTarget`: controlled composition of descriptor, architecture,
  optional snapshot and provenance.
- `ExecutionContext`: operation context for engine, target, measurement policy,
  shots and options.

Missing physical information is represented explicitly with the shared absence
states:

- `known`;
- `unknown`;
- `unavailable`;
- `not_applicable`;
- `unsupported`;
- `not_loaded`;
- `collection_error`.

The model does not infer T1, T2, fidelity, queue, timing, calibration or
connectivity when those values are not supplied.

## Targets and providers

`CQ.manual_target(...)` creates a neutral target declared by the user. It
requires explicit computational nature such as `physical`, `simulator_ideal`,
`simulator_noisy`, `hypothetical`, or `unknown`.

Manual data source is represented as provenance, not as the target nature.
Manual physical targets are marked as user-declared and not provider-verified.
Calibration is not considered current unless the user supplies a timestamped
snapshot and provenance.

The Qiskit provider adapter is an anti-corruption layer. It can convert a
Qiskit object explicitly supplied by the caller into the neutral target model.
It does not authenticate, list remote backends, open network connections,
select a backend or start jobs. It classifies physical backends, simulators and
structural Qiskit targets only when that information is available from the
explicit object.

`HardwareService.serialize(...)` emits JSON-compatible neutral data, and
`deserialize(json.loads(json.dumps(payload)))` reconstructs the neutral target
types, including topology, native instructions, `TargetDatum` values, timestamps
and schema version. Unknown schema versions fail explicitly.

## Compile and run integration

`CQ.compile(..., target=None, context=None)` and
`CQ.run_engine(..., target=None, context=None)` accept target/context data
additively. Calls without target keep the previous behavior.

When a target is supplied:

- `HardwareService` resolves it into an `ExecutionContext`;
- `CircuitService` extracts descriptor and requirements;
- `CompatibilityReport` records circuit, engine and target information;
- `CompiledArtifact` keeps the context, report and architecture fingerprint.

The system does not claim physical executability. Reports distinguish missing
target operations, arity mismatches, paradigm mismatches, unknown hardware data
and whether placement/routing/scheduling were not required, may be required or
were not analyzed.

`run_engine(..., target=...)` fails explicitly unless an executor-target binding
is implemented and recorded. This prevents results produced on default local
devices such as `AerSimulator`, `default.qubit`, Cirq Simulator or Braket
LocalSimulator from being attributed to a different declared target. A physical
target always fails before execution in this run.

## Current limitations

This run intentionally does not implement:

- PDF, slides, images or binary diagrams;
- Semantic IR;
- Circuit IR v2;
- Navigation v2;
- placement;
- routing;
- scheduling;
- physical optimization;
- automatic target selection;
- automatic engine selection;
- automatic unitary decomposition or synthesis;
- remote provider discovery;
- authentication;
- credential storage;
- new engines;
- new algorithms;
- new encodings;
- new remote execution.

Qiskit remains mandatory and the default engine in `0.1.x`. Optional engines
remain lazy. CUDA-Q remains non-operational unless a future run proves a
compatible environment and functional ports.
