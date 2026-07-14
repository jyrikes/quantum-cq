# Multi-Engine Foundation

Run 1 adds a small multi-engine layer without changing the existing Qiskit-first
public behavior.

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

The private `_engines` package separates:

- capability declaration;
- minimal lowering;
- native emission;
- compilation;
- execution;
- result normalization.

Optional SDKs are imported only inside their adapters. Importing `quantum_cq`
does not import PennyLane, Cirq, Braket, CUDA-Q, Aer or IBM Runtime.

## MCX Policy

The Navigation implementation does not choose engine-specific MCX
decomposition.

The Run 1 lowering policy is:

- zero controls: lower to `X`;
- one control: lower to `CX`;
- two controls: lower to `CCX`/Toffoli when supported;
- more controls: delegate only to an engine with tested native support;
- otherwise raise `CapabilityMismatchError`.

No ancilla-based decomposition, placement or routing is introduced in Run 1.
