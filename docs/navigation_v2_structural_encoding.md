# Navigation Encoding V1/V2

This document describes the RUN 4.3 two-stage navigation encoding layer.

## V1 remains the default

Navigation V1 is the existing addressed-memory implementation:

```text
U_D |a>|b> = |a>|b XOR D[a]>
```

The following public APIs keep their existing V1 behavior:

- `CQ.memory(...)`
- `CQ.nav(...)`
- `CQ.addressed(...)`
- `CQ.graph(...)`
- `CQ.graph_nav(...)`
- `CQ.walk(...)`
- `CQ.navigation(...)`
- `CQ.available_navigation_encodings()`

V1 remains the stable baseline for addressed memory, graph navigation and the
finite coined walk. V2 does not replace it.

## V2 entry point

Navigation V2 is selected explicitly:

```python
result = CQ.navigation_v2(
    heap,
    operation="read",
    selector=StructuralSelector.value("payload"),
)
```

Each call builds one concrete operation. The supported operations are:

- `read`
- `next`
- `parent`
- `child`
- `neighbor`
- `compare`

`operation` is required. `predicate` is accepted only for `compare`.

## Structural source

The supported domain is a finite typed heap:

- `StructuralType`
- `StructuralField`
- `StructuralNode`
- `StructuralHeap`
- `StructuralPointer`
- `StructuralSelector`

Fields must declare semantic roles when they are used by structural navigation.
The initial roles are:

- `value`
- `reference`
- `next`
- `parent`
- `child`
- `neighbor`

Selectors use those roles. A field named `next` is not treated as next unless it
declares `semantic_role="next"`.

## Canonicalization

RUN 4.3 canonicalization is exact for the supported finite domain. It explores
admissible node renamings up to a configured limit, serializes each candidate
deterministically and selects the lexicographically smallest representation.

The result preserves:

- roots;
- type IDs;
- semantic roles;
- scalar values;
- references;
- null;
- sharing;
- supported cycles;
- semantic ordering for ordered fields.

If the candidate limit is exceeded, no canonical fingerprint is emitted.

## `rho_D`

The resolver operates on the canonical structure. It returns a contextual
`RhoDResult`, not a raw integer. The result records:

- input canonical pointer;
- selector;
- resolved canonical pointer or value location;
- status;
- null state;
- diagnostics;
- provenance.

The finite `rho_D` table is stored in the `StructuralNavigationPlan` and is part
of the plan fingerprint metadata.

## Reversible embeddings

V2 uses reversible embeddings:

```text
read:       |p>|a>|b> -> |p>|a>|b XOR D[rho_D(p,a)]>
navigation: |p>|a>|q> -> |p>|a>|q XOR encode(rho_D(p,a))>
compare:    |inputs>|r> -> |inputs>|r XOR predicate(inputs)>
```

The implementation keeps pointer input registers unchanged and writes outputs to
separate XOR accumulators.

## Lowering

The initial concrete lowering strategies are:

- `explicit_exact`
- `sparse_exact`
- `oracle_model`

`explicit_exact` and `sparse_exact` lower V2 tables through Navigation V1
`AddressedMemory` / XOR-load and then produce the current `CircuitIR`.

The metadata records:

- `navigation_version_source="v2"`
- `lowering_backend="navigation_v1"`
- V1 engine used;
- finite resolution table;
- register layout;
- equivalence fingerprint;
- `exactness="exact"`.

`oracle_model` is abstract and does not produce a physical `CircuitIR`.

## Pipeline

`StructuralNavigationResult` enters the pipeline only through an explicit adapter:

```python
pipeline_result = CQ.pipeline(structural_navigation=result).transpile()
```

The V2 stages are:

- `navigation_v2_validate`
- `navigation_v2_canonicalize`
- `navigation_v2_plan`
- `navigation_v2_lower`
- `navigation_v2_verify`

After lowering, the existing unified pipeline handles placement, routing,
scheduling, native transpilation, compilation and execution.

## Limits

RUN 4.3 does not implement:

- update operations;
- dynamic allocation;
- garbage collection;
- infinite heaps;
- approximate structural encoding;
- lossy compression;
- general efficient graph canonicalization;
- joint representation-placement optimization;
- physical QRAM;
- CircuitIR v2;
- a new engine;
- remote execution or automatic backend selection.

The implementation is exact and finite. It does not claim quantum advantage,
scalability or universal absence of observational collisions.

