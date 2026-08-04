# Unit-Aware Resolution in USD: Implementation Exploration

Copyright &copy; 2026, NVIDIA Corporation, version 0.1 (DRAFT)

Jens Jebens

Companion to [Units and Scale in Composed Scenes](../units_and_scale/README.md),
which holds the problem statement, design principles, and open questions.
This document collects the implementation evidence: a proof-of-concept
consumer API, prim-level metrics schemas with a dimensional exponent
registry, and evaluation-time unit resolution through OpenExec and Hydra.
It exists to test whether the design directions in the problem statement
survive implementation, and to attach measured costs to the open
questions. Nothing here proposes OpenUSD behavior changes; default
behavior remains numeric-preserving throughout.

## Contents

- [Units API proof of concept](#units-api-proof-of-concept)
- [Evaluation-time unit resolution: OpenExec and Hydra integration](#evaluation-time-unit-resolution-openexec-and-hydra-integration)

## Units API proof of concept

A proof-of-concept Python library implementing the mechanisms described
in the problem statement is available at:

**[`extras/units_api` on the `jjebens/units-api-poc` branch](https://github.com/jensjebens/OpenUSD/tree/jjebens/units-api-poc/extras/units_api)**

The POC validates the three-layer design empirically — MetricsAPI
(prim-level unit declarations with ancestor inheritance), a dimensional
registry (schema-level exponent mappings), and per-attribute metadata
(self-describing annotations for custom attributes) — plus two consumer
APIs: **UnitsLens** for unit-aware attribute get/set and
**MetricsAssembler** for non-destructive corrective transforms at
reference boundaries.

### Key findings

- **Prim-level MetricsAPI is the right primary mechanism.** For a
  representative stage, 2 prim-level annotations achieve the same
  correctness as 66 per-attribute annotations (33× less overhead).
- **Per-attribute metadata is essential for custom attributes.** The
  dimensional registry cannot know about pipeline-specific attributes;
  per-attribute annotation makes them self-describing.
- **Dimensional exponents are schema-invariant.** Every
  `xformOp:translate` is L¹, every `physics:density` is M¹·L⁻³.
  This never changes per-prim and belongs in schema definitions.
- **Assembly correction and UnitsLens compose correctly.** Corrective
  `xformOp:scale` for transforms plus UnitsLens for derived quantities
  provides complete coverage.
- **Animation curves require tangent slope scaling.** For bezier
  splines, values and slopes scale by the unit ratio; tangent widths
  (time) are preserved.

### Scope

The implementation covers ~1,100 lines of library code (including
`bake_to_units`), ~2,000 lines of tests (133 tests across 6
programmatic test stages), and a dimensional registry of 26 entries
spanning transforms, camera, lights, physics, and PointInstancer
attributes. Built against OpenUSD 26.3.

The POC has been validated inside **Omniverse Kit 110** as a Kit
extension (`omni.units_api`) with 35 passing headless tests covering
all six attribute domains plus `bake_to_units` end-to-end scenarios.
The Kit integration also includes a **Units Inspector window** (showing
effective metrics, unit-bearing attribute conversions, and
audit/correct/bake actions) and **Blender-style unit annotations** in
the property panel — inline SI-converted values next to authored
numbers. The Kit integration is available at
[`jensjebens/omni-units-api`](https://github.com/jensjebens/omni-units-api).

In addition to the per-attribute lens and assembly correction, the POC
includes a **`bake_to_units()`** function that demonstrates the
non-destructive variant of "convert at ingest" described in open
question 2: all unit-bearing attribute values are converted and written
as overs in a session sublayer, so downstream consumers see correct
values with plain `attr.Get()` without needing the unit-aware API.
The original layer is untouched; removing the override layer reverts
the conversion.

The POC is built on a shared C++ foundation
([`jjebens/metrics-api-core`](https://github.com/jensjebens/OpenUSD/tree/jjebens/metrics-api-core/extras/usd/metricsApiCore))
that provides real USD applied schemas (`UsdGeomMetricsAPI`,
`UsdPhysicsMetricsAPI`), a plugin-discoverable dimensional exponent
registry via `plugInfo.json`, and ancestor-walk resolution functions
with Python bindings. The Python POC is a portable implementation for
environments without the C++ core; the C++ core serves OpenExec and
Hydra consumers. Both share symmetric tests to ensure the
implementations remain equivalent.

### Branch architecture

```
release (v26.03)
  └── jjebens/metrics-api-core           ← C++ schemas + dimensional registry + Python bindings
        ├── jjebens/units-api-poc        ← Python Units API (UnitsLens, MetricsAssembler, bake_to_units)
        └── jjebens/units-aware-value-resolution  ← OpenExec + Hydra (next section)
```

The Kit extension ([`jensjebens/omni-units-api`](https://github.com/jensjebens/omni-units-api))
vendors the Python POC and adds Kit-specific UI (Units Inspector window,
property widget annotations). It runs against stock USD (no fork
required).

## Evaluation-time unit resolution: OpenExec and Hydra integration

This section documents the proof-of-concept implementation of
evaluation-time unit resolution, covering the full stack from OpenExec
computation through Hydra scene index integration to rendered output.

### Before and after

The following renders demonstrate the problem and the solution on a
meter-scale factory stage with centimeter-scale and millimeter-scale
referenced assets:

**Before** (no units resolution): Only the blue 1 m reference cube is
visible. The red cm-scale box is 200 m away and the green mm-scale box
is 2 km away — both invisible at this camera distance.

**After** (with units resolution): All three cubes are visible at the
correct positions and sizes — blue (1 m), red (50 cm → 0.5 m), green
(500 mm → 0.5 m).

Images and demo scenes are available at
[`extras/exec/examples/unitsDemo/`](https://github.com/jensjebens/OpenUSD/tree/feature/exec-hydra-scene-filter/extras/exec/examples/unitsDemo).

### Architecture

The implementation consists of three independent components that
compose into a clean evaluation-time pipeline:

```
UsdGeomMetricsAPI (metrics:metersPerUnit on prim)
  → execMetricsUnits (computeUnitAwareLocalToWorldTransform)
    → HdExecComputedTransformSceneIndex (generic exec→Hydra bridge)
      → HdFlatteningSceneIndex → correct world-space transforms
```

#### 1. UsdGeomMetricsAPI — prim-level unit declarations

Real USD applied API schemas declaring the unit context for a prim's
subtree, implemented on the
[`jjebens/metrics-api-core`](https://github.com/jensjebens/OpenUSD/tree/jjebens/metrics-api-core/extras/usd/metricsApiCore)
branch:

```usda
def Xform "CmRobot" (apiSchemas = ["GeomMetricsAPI"]) {
    double metrics:metersPerUnit = 0.01
    token metrics:upAxis = "Y"
}
```

- `UsdGeomMetricsAPI` — `metrics:metersPerUnit`, `metrics:upAxis`
- `UsdPhysicsMetricsAPI` — `metrics:kilogramsPerUnit`
- `UsdMetricsDimensionalRegistry` — singleton loaded from
  `plugInfo.json`, maps attribute names to L/M/T exponents
- `UsdMetricsGetEffectiveMetersPerUnit()` — C++ ancestor walk
  resolution with Python bindings

Values inherit down the hierarchy. Applying to a root prim establishes
the unit context for the entire subtree. Aligns with the MetricsAPI
direction proposed in PR #45.

#### 2. execMetricsUnits — OpenExec computation

Registers `computeUnitAwareLocalToWorldTransform` on
`UsdMetricsGeomMetricsAPI`:

```cpp
EXEC_REGISTER_COMPUTATIONS_FOR_SCHEMA(UsdMetricsGeomMetricsAPI)
{
    self.PrimComputation(computeUnitAwareLocalToWorldTransform)
        .Callback<GfMatrix4d>(&_ComputeUnitAwareL2W)
        .Inputs(
            Computation<GfMatrix4d>(computeLocalToWorldTransform),
            AttributeValue<double>(metrics:metersPerUnit)
        );
}
```

The computation reads `computeLocalToWorldTransform` from execGeom
(cross-schema, same prim) and `metrics:metersPerUnit` from
GeomMetricsAPI. It applies **uniform scaling** — both the upper-left
3×3 (rotation/scale) and the translation row — so that a 20 cm cube
referenced into a meter stage renders at 0.2 m size as well as at the
correct position.

Source:
[`extras/exec/examples/metricsUnits/`](https://github.com/jensjebens/OpenUSD/tree/feature/exec-hydra-scene-filter/extras/exec/examples/metricsUnits)

#### 3. HdExecComputedTransformSceneIndex — generic exec→Hydra bridge

A `HdSingleInputFilteringSceneIndexBase` that overlays exec-computed
transforms onto `HdXformSchema` data sources. This is **shared
infrastructure** used by three independent projects:

- **Units resolution** — `computeUnitAwareLocalToWorldTransform`
  with `resetXformStack = false` (local-space correction)
- **Newton physics simulation** — `computeSimulatedTransform`
  with `resetXformStack = true` (world-space replacement)
- **Dynamic spatial ownership** — ownership transforms
  with `resetXformStack = true` (world-space replacement)

Per-schema `resetXformStack` is declared in `plugInfo.json` metadata.
The filter supports auto-bootstrap (discovers stage via
`SetGlobalStage`), `TransformProvider` callbacks for side-effect-driven
computations, and `AdvanceGlobalTime` for frame-by-frame evaluation.
The `UsdImagingGLEngine` integration calls `SetGlobalStage` and
`AdvanceGlobalTime` on each frame.

Source:
[`pxr/imaging/hdExec/`](https://github.com/jensjebens/OpenUSD/tree/feature/exec-hydra-scene-filter/pxr/imaging/hdExec)

### Summary of findings

1. **Evaluation-time unit resolution is feasible and validated
   end-to-end.** The full pipeline — MetricsAPI schema attributes →
   OpenExec computation → HdExec scene index filter →
   HdFlatteningSceneIndex → correct world-space transforms — has been
   tested with `(100, 0, 50)` cm correctly producing `(11, 0, 0.5)` m
   in world space (including parent accumulation).

2. **MetricsAPI is confirmed as a hard prerequisite** and has been
   implemented as real USD applied schemas (`UsdGeomMetricsAPI`,
   `UsdPhysicsMetricsAPI`) with C++ ancestor walk resolution and
   Python bindings.

3. **Uniform scaling is required**, not just translation scaling. A
   prim authored in centimeters and referenced into a meter-scale
   stage needs both its position and its size corrected.

4. **The dimensional registry is plugin-discoverable.** Attribute
   exponents are declared in `plugInfo.json`, not hardcoded. Each
   schema domain contributes its own entries; third-party schemas
   register via their own `plugInfo.json`.

5. **Performance overhead seems manageable.** At 10,000 prims, unit-aware
   computation adds 0–5% overhead compared to the standard transform
   computation.

6. **The HdExec filter is shared infrastructure** validated by three
   independent projects. Per-schema metadata (`resetXformStack`,
   `allowsPluginComputations`) enables clean multi-consumer operation
   without hardcoded schema names.

7. **A bug in execGeom was discovered and reported.** The
   `xformOp:transform` attribute name was misspelled as
   `xformOps:transform` in execGeom's `xformable.cpp`. This caused
   `computeLocalToWorldTransform` to return identity for any standard
   `UsdGeomXformable`-authored transform. The bug was independently
   fixed by Pixar on the `dev` branch (cc5ca4d812, 2026-03-23).

### Omniverse / Kit integration

For Omniverse Kit, the rendering pipeline uses Fabric (a flat,
cache-friendly scene representation) rather than the Hydra scene index
chain. The HdExec scene index filter works for Storm (traditional
Hydra path) but does not affect the RTX renderer when Fabric is the
primary path.

A Kit extension (`omni.units.resolution`) demonstrates Fabric-level
correction using:

- **USDRT** for O(1) prim discovery (`GetPrimsWithAppliedAPIName`)
  and transform read/write (`usdrt.Rt.Xformable`)
- **Warp GPU kernels** for parallel unit scaling of N transforms
- **SchemaChangeWatcher** for live reactivity to stage edits
  (`Usd.Notice.ObjectsChanged` with next-frame debounce)

The Kit extension writes corrected transforms directly to Fabric's
`_localMatrix` and `omni:fabric:worldMatrix` attributes, which the
RTX renderer reads. Session-layer correction via `MetricsAssembler`
remains the established approach for compatibility with all consumers.

### Limitations and future work

1. **upAxis Y↔Z rotation** — The computation architecture for upAxis
   correction is implemented (self-referencing `NamespaceAncestor` for
   inherited resolution, same pattern as `execGeom`'s L2W), but is
   blocked by an OpenExec program state conflict when multiple prims
   with exec computations are evaluated sequentially via
   `HdExecComputedTransformSceneIndex`. See
   [jensjebens/OpenUSD#4](https://github.com/jensjebens/OpenUSD/issues/4)
   for details and reproduction steps. `metersPerUnit` correction works
   end-to-end.

2. **Camera, light, and physics attributes** beyond transforms are
   not yet covered by the Hydra integration but follow the same
   dimensional analysis pattern via the `DimensionalRegistry`.

### Source code

| Component | Branch | Path |
|---|---|---|
| MetricsAPI schemas | `jjebens/metrics-api-core` | `extras/usd/metricsApiCore/` |
| OpenExec computation | `feature/exec-hydra-scene-filter` | `extras/exec/examples/metricsUnits/` |
| HdExec scene index | `feature/exec-hydra-scene-filter` | `pxr/imaging/hdExec/` |
| Demo scenes + renders | `feature/exec-hydra-scene-filter` | `extras/exec/examples/unitsDemo/` |
| Kit extension (Warp) | workspace | `kit-investigation/omni.units.resolution/` |
| Kit extension (Python API) | [`jensjebens/omni-units-api`](https://github.com/jensjebens/omni-units-api) | `source/extensions/omni.units_api/` |
| PR #1 | `feature/exec-hydra-scene-filter` → `dev` | [jensjebens/OpenUSD#1](https://github.com/jensjebens/OpenUSD/pull/1) |
| OpenExec multi-prim issue | — | [jensjebens/OpenUSD#4](https://github.com/jensjebens/OpenUSD/issues/4) |
