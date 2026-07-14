# RUN 4.2 - Pipeline, Qiskit topology and exact coined walk

## Summary

RUN 4.2 closes the incomplete contracts from RUN 4 and keeps the existing public surface:
`CQ.pipeline(...)`, `CQ.walk(...)`, `CQ.manual_target(...)`, `CQ.compile(...)`, `CQ.run_engine(...)`,
`PipelineResult`, `CircuitIR` and `OperatorCircuit`.

The run does not introduce a second pipeline, a new engine, `CircuitIR v2`, Navigation v2, remote
hardware discovery, credentials, visual artifacts, PDF files or automatic backend selection.

## Unified Pipeline

Each `PipelineScenario` now carries its effective configuration: global configuration plus explicit
scenario overrides. Stages consume that effective configuration for parameters, symbols, target,
snapshot, engine, shots, measurement policy, planning strategies, native transpilation policy and
runtime options.

`stages` and `stop_after` are operational controls. A disabled stage is recorded explicitly as
`not_requested`; a stage skipped after `stop_after` is recorded as `skipped_by_policy`. A stage marked
`completed` must have produced all features declared in `provides`.

The enriched execution path is compile-once:

```text
circuit -> CompiledArtifact -> exact same CompiledArtifact -> EngineResult
```

`PipelineCore.run_engine()` uses `EngineService.compile_for_execution(...)` and then executes the
resulting artifact directly. The Qiskit executor records the artifact object identity in result
metadata for testable provenance.

## Planning

Placement remains deterministic and limited to the current strategies, including `identity` and
`first_available`.

Routing now materializes a new `CircuitIR` when it inserts SWAPs or changes mappings. The routing plan
preserves initial and final mappings, inserted SWAPs, provenance and the routed circuit. Routing does
not decompose SWAP into CX gates. If SWAP is unavailable on the physical edge, routing fails explicitly.

Scheduling consumes `routing_plan.routed_circuit` when routing has run. It does not invent durations:
missing duration data produces `insufficient_information`.

Circuit fingerprints now include semantic operation data such as parameters, labels, metadata and
unitary matrices.

## Qiskit Topology

The existing Qiskit hardware adapter remains the only conversion path. It accepts explicit local
objects such as `qiskit.transpiler.Target`, compatible backend objects exposing a `Target`, and
recognized `CouplingMap` objects. It does not perform network access or remote discovery.

For `Target`, extraction uses operation names, instruction objects and qargs. The architecture stores
stable structural data:

- physical qubits;
- native instructions;
- arity and valid qargs;
- directed topology edges;
- operation names valid on each edge;
- structural support for measurement/reset where available.

Temporal and calibration-like data, such as duration and error, are stored in `TargetStateSnapshot`.
The adapter records Qiskit version, source object, transformed fields, omitted fields, warnings,
completeness and timestamp in provenance. A standalone `Target` is structural and is not treated as an
executor-bound backend.

## Exact Coined Walk

`CQ.walk(graph, steps=1)` is preserved. The implementation behind it is now an exact finite
discrete-time coined quantum walk using:

```text
W = S C
```

This means local coin first, then flip-flop shift. For `t` steps the evolution is `(S C)^t`.

The internal `WalkTopology` describes vertices, deterministic neighbor order, local ports, reverse
ports, arcs, edges, valid states, padding states, isolated vertices and a fingerprint. It is specific
to the coined walk and is not a general Navigation v2 canonical structure.

Supported coins in this run:

- `grover` as the default local coin;
- `identity`;
- `hadamard` only when the local coin space has no padding and dimension is compatible;
- custom unitary coins only when the declared matrix matches the full physical coin space and does not
  mix with padding.

The flip-flop shift maps `|v,c>` to `|u,c_reverse>` for valid arcs and leaves invalid/padding states
unchanged. It is validated as a bijective permutation of the full physical basis.

The implemented lowering strategy is `dense_exact`. It computes dimension before allocation and rejects
plans above the configured maximum dimension with a typed capacity error. The lowering target is the
existing `CircuitIR`; no new IR is introduced.

## Graph Separation

RUN 4.2 preserves three separate graph concepts:

- `G_data`: the input graph for the walk.
- `G_circuit`: logical circuit interactions after lowering.
- `G_physical`: hardware topology from `ExecutionTarget.architecture.topology`.

No direct mapping from a data vertex to a physical qubit is implied. Placement still operates on the
logical qubits of the lowered circuit.

## Remaining Limits

This run does not implement Navigation v2, graph canonicalization, weighted or dynamic graphs,
continuous-time walks, Szegedy walks, quantum walk search, decoherence, remote hardware jobs, automatic
target selection, fidelity estimation, speedup claims or hardware-aware walk synthesis.
