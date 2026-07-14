# Run 2: Engine Contracts And Component Catalog

Run 2 starts from branch `run-1-navigation-v1-multi-engine` at commit
`b4973c7`. The pre-existing local notebook change in
`notebooks/quantum_cq_simple_api_lab.ipynb` remains outside the run changes.

Baseline before edits:

- `python -m pytest -q`: 196 passed, 6 skipped, 24 warnings;
- `python -m compileall -q src tests`: passed;
- `python -m build`: passed.

## Engine Architecture

The private multi-engine layer is organized as:

```text
CQ facade
  -> EngineService
  -> EngineBundle
  -> AvailabilityPort / CapabilitiesPort / EmitterPort / CompilerPort /
     ExecutorPort / ResultDecoderPort
```

The bundle is immutable and rejects mixed engine IDs. The service coordinates
the flow but does not import optional SDKs or concrete component classes. SDK
imports stay inside the concrete engine modules.

## Data Contracts

The following common objects remain SDK-free:

- `EngineAvailability`;
- `MeasurementContract`;
- `CompiledArtifact`;
- `EngineResult`;
- `CompatibilityReport`;
- `CatalogEntry`;
- `ComponentRequirement`.

`CompiledArtifact` preserves the emitted object, compiled native object,
backend/device, options, metadata, measurement contract, considered
capabilities, lowering rules and engine version when available.

`EngineResult` preserves raw native results and records canonical bit order,
native bit order, endianness and whether normalization was applied.

## Measurement

The canonical count convention is independent of any SDK: count strings are
ordered by descending classical bit index. This preserves the public Qiskit
behavior but is not defined as a Qiskit-owned rule.

`CQ.emit()` and `CQ.compile()` do not add measure-all automatically.
`CQ.run_engine()` may add measure-all before compilation for that execution
only, when no explicit measurement exists and the measurement policy allows it.

## Component Catalog

`CQ.catalog()` returns read-only `CatalogEntry` objects derived from descriptors
stored with the existing registries. The catalog does not register components,
execute factories, mutate registries, load optional SDKs or expose internal
classes as public API.

`CQ.oracle(name, *args, **kwargs)` resolves the existing `OracleRegistry`,
forwards construction arguments and returns a new instance per call when the
oracle can hold state.

## Engine-Aware Representatives

Run 2 validates logical construction for a limited representative set:

- state encoding: `basis`;
- oracle: `phase_marked_state`;
- primitive/operator: `standard_diffuser`;
- algorithm: `deutsch`;
- navigation: `addressed_memory`.

For optional engines these representatives build `CircuitIR` through
`LogicalCircuitFactory` and report `circuit_format="ir"`. The run does not
promise full portability for all components.
