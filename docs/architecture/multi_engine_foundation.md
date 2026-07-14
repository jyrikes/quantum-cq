# Multi-Engine Foundation

Run 2 keeps the Run 1 public API and refactors the private engine layer into
cohesive ports, bundles and a service layer. Public behavior remains
Qiskit-first.

## Policy

- Qiskit remains a required dependency, the default engine and the reference
  implementation for `0.1.x`.
- `CQ.run(...)`, `CQ.to_qiskit(...)`, `CQ.export(..., target="qiskit")` and
  `CQ.available_exporters()` keep their existing meanings.
- `CQ.available_exporters()` remains the legacy Qiskit exporter list and returns
  `["qiskit"]`.
- The new engine layer is exposed through `CQ.engines()`.

## APIs

```python
CQ.engines()
CQ.engine_capabilities(engine)
CQ.emit(circuit_like, engine="qiskit", **options)
CQ.compile(circuit_like, engine="qiskit", **options)
CQ.run_engine(circuit_like, engine="qiskit", shots=1024, **options)
```

Responsibilities:

- `emit`: convert a supported logical circuit to the native engine object;
- `compile`: return a `CompiledArtifact` with engine, emitted circuit, native
  compiled object, backend/device, options and metadata;
- `run_engine`: execute synchronously and return an `EngineResult` preserving
  normalized data and the native raw result.

## Logical Input

Optional engines consume the existing `CircuitIR` or `QC` compact circuit model.
They do not receive Qiskit circuits as an interchange format. Passing a Qiskit
object to an optional engine raises an explicit emission error.

Navigation v1 can be built with `LogicalCircuitFactory`, which produces
`CircuitIR` and keeps the Navigation semantics independent from a concrete
Qiskit builder. Qiskit remains the default factory and default export target.

## Layer Boundaries

The private `_engines` package now separates ports with one responsibility each:

- `AvailabilityPort`: installation, environment compatibility, version and
  unavailability reason;
- `CapabilitiesPort`: capability declarations for the new multi-engine layer;
- `EmitterPort`: `CircuitIR` to native engine object;
- `CompilerPort`: native object to `CompiledArtifact`;
- `ExecutorPort`: synchronous execution of a compatible artifact;
- `ResultDecoderPort`: native result to `EngineResult`.

Optional SDKs are imported only inside their adapters. Importing `quantum_cq`
does not import PennyLane, Cirq, Braket, CUDA-Q, Aer or IBM Runtime.

`EngineBundle` is an immutable Abstract Factory result that composes coherent
ports for one `engine_id`. It rejects mixed-engine ports. `EngineService`
orchestrates public engine APIs and delegates all concrete behavior to ports.

## Measurement Contract

Run 2 defines an SDK-independent canonical bit convention:

- count strings are ordered by descending classical bit index;
- the highest clbit appears on the left;
- the lowest clbit appears on the right;
- partial measurements preserve the explicit qubit-to-clbit mapping;
- unmeasured clbits are not invented silently.

`CQ.emit()` and `CQ.compile()` do not add measure-all automatically.
`CQ.run_engine()` may prepare measure-all only when no explicit measurement is
present and the execution policy allows it. That decision is recorded in
`MeasurementContract`, `CompiledArtifact` and `EngineResult`.

## Compatibility

Component requirements are evaluated against engine capabilities by a
Specification-style `CompatibilityEvaluator`. It returns a descriptive immutable
`CompatibilityReport`. The evaluator does not lower, emit, compile, execute,
decode or instantiate components.

## MCX Policy

The Navigation implementation does not choose engine-specific MCX
decomposition.

The Run 1 lowering policy is:

- zero controls: lower to `X`;
- one control: lower to `CX`;
- two controls: lower to `CCX`/Toffoli when supported;
- more controls: delegate only to an engine with tested native support;
- otherwise raise `CapabilityMismatchError`.

No ancilla-based decomposition, placement or routing is introduced in Run 2.

## Component Catalog

`CQ.catalog()` exposes a read-only projection of descriptors stored with the
existing registries. Registries remain the operational source of truth. The
catalog does not execute factories, load optional SDKs, mutate registries or
expose internal classes as public API.

`CQ.oracle(name, *args, **kwargs)` uses `OracleRegistry` and forwards
construction arguments so existing oracles can be configured without importing
internal classes.
