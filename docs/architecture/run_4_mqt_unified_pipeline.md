# RUN 4: MQT DSL and Unified Pipeline

Baseline:

- Branch base: `run-3-hardware-abstraction-circuit-integration`
- HEAD base: `6b12c13e533f61b1e9ed7bf3f92e7bc6ef3ef8cc`
- Package version: `0.1.2`
- Qiskit remains mandatory and the default engine.
- Optional engines remain lazy.

## Pipeline Contract

RUN 4 keeps the existing public pipeline and adds a single internal
orchestration core. The following entry points delegate to that core when an
enriched flow is requested:

- `CQ.pipeline(...).transpile()`
- `CQ.pipeline(...).compile()`
- `CQ.pipeline(...).run_engine()`
- `BenchmarkingPipeline` native transpilation

The legacy encoding flow remains distinct:

```python
encoded = CQ.pipeline([1, 0, 1], encoding="basis").build()
same = CQ.pipeline([1, 0, 1], encoding="basis").run()
```

Both calls still return `EncodedCircuit`. MQT, planning, native transpilation
and engine execution are not started by a pure `data` plus `encoding` flow.

Each enriched execution has exactly one primary input:

- `data`
- `equation`
- `circuit`
- `input` with an explicit `input_adapter`

Conflicting primary inputs fail before stages run. Runtime features such as
engine, target, snapshot, parameters, symbols, strategies, shots and
measurement policy are complementary features, not primary inputs.

## MQT DSL

The first executable MQT grammar is intentionally small and deterministic. It
accepts one state assignment plus optional final measurements:

```text
|psi> := CX[q0,q1] * (H[q0] tensor I[q1]) * |00>
measure Z[q0,q1] -> c[0,1]
```

Unicode aliases are canonical:

- `|psi>` maps to `|ψ⟩`
- `*` maps to `·`
- `tensor` maps to `⊗`
- `dagger` maps to `†`
- `theta` and `phi` map to parameter aliases

The parser does not use `eval()` and rejects Python-like constructs, imports,
multiple assignments, loops, conditionals, macros and the pipeline operator.

The MQT layers are separate:

- AST preserves source structure and positions.
- Semantic IR resolves symbols, arity, dimensions, parameters and
  requirements.
- Lowering produces a new `CircuitIR`.

No level is mutated to become the next level.

## Planning And Transpilation

RUN 4 separates neutral and native transpilation.

Neutral stages:

- semantic and logical lowering
- placement
- routing
- scheduling

Native stage:

- `TranspilerPort` receives emitted native circuits and returns before/after
  native artifacts, status, mappings, metrics and metadata.

Qiskit has a real `TranspilerPort`. Without an explicit backend or pass
manager it records an identity native transpilation. PennyLane, Cirq and
Braket expose explicit ports with honest `not_applicable` behavior until a
tested native transpilation flow exists.

Planning is deliberately initial:

- placement supports deterministic `identity` and `first_available`;
- routing respects directed topology and requires SWAP support;
- scheduling supports ASAP only when durations are known.

The planner does not implement SABRE, global routing optimization, pulse
compilation, pulse scheduling or automatic target selection.

## PipelineResult

`PipelineResult` remains compatible with the experiment pipeline. Enriched
pipeline data is added by composition through scenario results:

- stage results
- circuit snapshots
- transformation graph
- metrics
- diagnostics
- semantic artifacts
- compiled artifact
- engine result

Convenience accessors such as `logical_circuit`, `before_transpile`,
`after_transpile`, `compiled_artifact` and `engine_result` work only for a
single scenario. Multiple scenarios require explicit `scenario_id`.

`to_dict()` and `to_json()` avoid serializing SDK objects directly. Native
circuits, backends, devices, callables, adapters and renderers are represented
by neutral descriptors or metadata summaries.

Text renderers are always available:

- `show_circuits()`
- `show_transformations()`
- `show_measurements()`

Graphical rendering is lazy and never writes PNG, SVG, PDF, HTML or other
visual files automatically.

## Limits

RUN 4 does not implement:

- a second public pipeline;
- CircuitIR v2;
- Navigation v2;
- full EncodingPlan;
- ML framework adapters;
- loops, conditionals or macros in MQT;
- universal state synthesis;
- universal unitary decomposition;
- SABRE;
- pulse-level compilation;
- remote discovery, authentication or execution;
- a new engine;
- optional Qiskit policy;
- automatic best target, engine or encoding selection;
- persistent visual artifacts.
