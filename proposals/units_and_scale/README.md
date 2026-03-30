# Units and Scale in Composed Scenes

Copyright &copy; 2026, NVIDIA Corporation, version 0.1 (DRAFT)

Jens Jebens

## Contents

- [Introduction](#introduction)
- [Motivation](#motivation)
  - [How USD handles units today](#how-usd-handles-units-today)
  - [The expanding ecosystem](#the-expanding-ecosystem)
- [Problem statement](#problem-statement)
  - [Three kinds of units](#three-kinds-of-units)
  - [Why software alone cannot standardize units](#why-software-alone-cannot-standardize-units)
  - [Why this matters now](#why-this-matters-now)
- [Existing mechanisms in USD](#existing-mechanisms-in-usd)
  - [Stage-level metrics metadata](#stage-level-metrics-metadata)
  - [Time remapping vs. spatial remapping](#time-remapping-vs-spatial-remapping)
  - [Metrics Assembler and Scene Optimizer](#metrics-assembler-and-scene-optimizer)
- [Industry use cases](#industry-use-cases)
  - [Manufacturing and digital engineering](#manufacturing-and-digital-engineering)
  - [Architecture, Engineering, Construction, and Operations (AECO)](#architecture-engineering-construction-and-operations-aeco)
  - [Robotics and simulation](#robotics-and-simulation)
  - [Media and Entertainment (M&E)](#media-and-entertainment-me)
- [Design considerations](#design-considerations)
  - [Principles](#principles)
  - [Open questions and tradeoffs](#open-questions-and-tradeoffs)
  - [Recommended baseline](#recommended-baseline)
  - [Risks](#risks)
- [Relationship to other proposals](#relationship-to-other-proposals)
- [Next steps](#next-steps)
- [Appendix A: What conversion does not cover](#appendix-a-what-conversion-does-not-cover)
- [Appendix B: AI-Assisted Drafting](#appendix-b-ai-assisted-drafting)
- [Appendix C: Units API Proof of Concept](#appendix-c-units-api-proof-of-concept)
- [Appendix D: Evaluation-Time Unit Resolution — OpenExec and Hydra Integration](#appendix-d-evaluation-time-unit-resolution--openexec-and-hydra-integration)

## Introduction

Regularly, and with increasing impatience,
someone asks why USD doesn't "just fix" units.
Scenes break, assets come in at the wrong scale,
simulations explode, and it feels like
the tooling should have solved this by now.
The frustration is legitimate.

Many systems that aggregate spatial data --
CAD tools, GIS platforms, game engines --
reconcile unit differences
as part of their composition or import model,
trading numeric preservation for unit consistency.
Systems that instead preserve authored numbers exactly,
as USD does,
gain non-destructive composition
but inherit the full burden of unit reconciliation
as an external, unsolved responsibility.
Users accustomed to the former
encounter the latter as an unexpected gap.

Solving this requires both ecosystem decisions --
what the canonical units are, who is responsible
for conformance, where the cost is paid --
and system infrastructure
that makes the agreed-upon architecture implementable.
Neither can proceed without the other.

**Expected outcome.** This proposal seeks community alignment on the
structure of the units problem -- distinguishing concerns that are
routinely conflated -- and on the design principles that should guide
solutions. The likely result is a combination of:

- **Ecosystem conventions** -- canonical units, conformance
  responsibilities.
- **Infrastructure changes** -- unit-dimension annotations in schemas,
  prim-level metrics, evaluation-time resolution.
- **Practical tooling** -- assembly-time correction, ingest validation,
  composed-space editing.

Several of these efforts are already underway; this proposal aims to
connect them under a coherent problem statement so they can proceed
without one blocking or distorting the other.

## Motivation

### How USD handles units today

OpenUSD's composition model -- sublayering, references, payloads,
variants, inherits -- is designed so that authored values survive
composition exactly as written. A weaker layer's opinion is a literal
numeric value; a stronger layer overrides it with another literal
numeric value. No composition arc reinterprets or transforms the numbers
it composes. This numeric-preserving property is what makes
non-destructive workflows, deterministic caching, and stable
round-tripping possible.

Spatial metrics are expressed as stage-level layer metadata:

- **`metersPerUnit`** -- a scale factor relating the stage's linear
  unit to meters (e.g., `0.01` for centimeters, `1.0` for meters).
- **`upAxis`** -- the stage's vertical axis convention (`Y` or `Z`).
- **`kilogramsPerUnit`** -- the stage's mass unit
  (used by `UsdPhysics`).

These metadata values are advisory: they inform consumers what unit
system the authored numbers are expressed in, but the composition
engine does not reconcile them. When a centimeter-scale asset is
referenced into a meter-scale stage, the authored numbers arrive
unchanged. The reference's `metersPerUnit = 0.01` is not composed
against the stage's `metersPerUnit = 1.0` to produce a corrective
scale factor. USD explicitly delegates unit reconciliation to
**assemblers, pipelines, and application-layer tooling** -- not to
the composition engine.

This is a deliberate design choice, not an oversight. Automatic spatial
normalization would require USD to know which numeric attributes are
lengths vs. angles vs. unitless, how to account for existing scale in
the composed transform stack (avoiding double-scaling), and how to do
so without breaking the guarantees that make non-destructive composition
work.

Unlike spatial units, USD *does* provide schema-agnostic remapping for
**time**: `SdfLayerOffset` applies an affine transformation (scale and
offset) to time-valued attributes at composition arc boundaries. The
asymmetry between time and space is not accidental -- time remapping
requires no knowledge of attribute semantics (all time values share one
dimension), while spatial remapping requires dimensional analysis
across heterogeneous attribute types.

### The expanding ecosystem

USD was born in visual effects and animation, where content originates
from DCC tools with largely consistent metric conventions. As USD
expands into new industries, it increasingly encounters data from
systems that made fundamentally different unit choices:

- **CAD and PLM systems** (SolidWorks, Creo, CATIA, NX) typically
  author geometry in millimeters. A bolt exported as USD from a CAD
  system carries shaft length values in the tens (millimeters), not in
  the hundredths (meters).
- **AECO tools** (Revit, Archicad, IFC) mix imperial and metric units,
  often within the same project. A building model may contain geometry
  authored in feet, millimeters, and meters.
- **GIS and infrastructure platforms** work in geographic coordinate
  systems (degrees) and projected coordinates (meters or feet) at
  scales spanning continents.
- **Game engines** (Unreal, Unity) typically use centimeters as their
  internal unit, producing assets whose numeric values are 100x larger
  than meter-scale equivalents.
- **Robotics simulators** (Isaac Sim, Gazebo) require precise metric
  consistency for physics simulation -- a 100x scale error in gravity
  or joint limits produces catastrophic simulation failure.

When these assets are composed into a single USD stage, the authored
numbers disagree. A factory floor assembling CAD-sourced parts
(millimeters), building structure (meters), and robotic work cells
(centimeters) has three different interpretations of `translate = 100`
within the same composed hierarchy.

## Problem statement

### Three kinds of units

When spatial data moves through a pipeline -- from authoring tools to
serialized files to runtime applications to user-facing displays -- the
concept of "units" applies at three distinct layers. Failing to
distinguish them is the root of most confused requirements and
misdirected solutions.

**Serialized units** (also called *encoded units* or *storage units*)
determine the numeric values written to disk. A 10 mm bolt stored in a
file whose linear unit is meters has a shaft length value of `0.01`.
The same bolt stored in millimeters has a shaft length value of `10.0`.
The physical object is identical; the stored number is not. Serialized
units are a commitment made at authoring or export time. Once data is
written, the choice is baked into every numeric value in the file.

**Working units** are the unit system in which an application performs
computation at runtime: transform evaluation, physics simulation,
intersection tests, measurement queries. Working units are an
application-layer concern. An application is free to convert serialized
values into any internal unit system at load time, perform all
computation in that system, and convert results back on write. This is
exactly what CAD systems do: SolidWorks stores geometry in a normalized
internal representation and converts to/from document units at I/O
boundaries. The choice of working units does not need to match the
serialized units of any particular data source.

**Display units** are the units shown to the user in property panels,
measurement tools, status bars, and overlays. Display units are purely a
presentation concern -- a screw encoded in millimeters, composed into a
railway system encoded in meters, can be measured and displayed in any
unit the user chooses without affecting any stored value or runtime
computation. Display units require no changes to data formats,
composition semantics, or serialization strategies. They are solved by
UI code.

The hard problems are all in the serialized and working unit layers.
Display units are trivial and are not discussed further.

### Why software alone cannot standardize units

The units problem persists not because the math is hard -- unit
conversion is exact -- but because three interrelated gaps reinforce
each other, preventing any single intervention from resolving the
problem.

**No one has agreed on canonical units.**
Before any conversion tool can do the right thing, someone must decide
what the right thing *is*: what the canonical units are, who is
responsible for conformance, and where the cost is paid. These are
standardization and governance questions, not software questions.
Every pipeline that has solved units internally did so by making
these decisions explicitly. This prerequisite requires no changes to
OpenUSD. It requires the community to converge on conventions.

**Attributes don't declare their units.**
Stage-level unit metadata (like `metersPerUnit`) exists, but individual
attributes do not declare whether they are unit-bearing or what their
dimensional exponents are. A density value, a displacement magnitude, a
texture's intended physical scale -- none carry annotations that
distinguish length from length³ from unitless. Software cannot convert
what it cannot identify; the information needed for correct conversion
is not in the data.

**Composition has no unit boundaries.**
Aggregation systems that preserve authored numbers exactly -- rather
than normalizing on import -- typically lack three structural
prerequisites for reliable unit reconciliation:

- Schemas do not declare which attributes are unit-bearing or what
  their unit dimensions are.
- Composition has no concept of a unit boundary at reference or
  aggregation points.
- There is no computational layer where "read this value in canonical
  units" can be expressed as part of value evaluation.

These are addressable gaps, but they require coordinated design work
across schema, composition, and evaluation layers.

These three gaps reinforce each other. Software cannot be designed
correctly until the ecosystem agrees on what it should do. The
ecosystem cannot converge until the software provides the mechanisms
to implement and enforce the agreement.

### Why this matters now

The urgency of the units problem has increased for several reasons:

1. **Cross-industry adoption.** USD's expansion into manufacturing,
   AECO, and robotics has brought content from systems with
   fundamentally different unit conventions into the same composed
   stages. The problem is no longer edge-case; it is the default
   condition for any multi-source assembly.

2. **Factory-scale composition.** Virtual factory workflows aggregate
   thousands of CAD-sourced assets (typically millimeters) into
   meter-scale stages. Without systematic unit handling, every stage
   open pays a deep-traversal correction cost that has been measured
   at 80--90 seconds on production stages, with full stage-open
   penalties exceeding 90 seconds.

3. **Physics simulation sensitivity.** Robotics and physics
   simulation workflows are intolerant of unit mismatches. A gravity
   constant of `9.81` in a centimeter-scale stage produces 100x the
   expected acceleration. Joint limits, velocities, and forces are
   all affected. Unlike visual workflows where a scale error is
   merely distracting, simulation failures are catastrophic and
   difficult to diagnose.

4. **Incomplete coverage of existing tools.** Current correction
   mechanisms (such as Omniverse's Metrics Assembler) handle
   transforms and a subset of physics attributes, but do not cover
   camera spatial attributes (clipping range, focus distance), light
   spatial attributes (length, radius, width, height), material
   spatial properties (displacement magnitude, SSS distances,
   volumetric density), or stage-level physics constants (gravity
   magnitude). Uncovered domains produce silently wrong results.

5. **The MetricsAPI proposal is active.** The Pixar proposal
   ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45))
   to move unit declarations from layer metadata to prim-level
   applied schemas is under active evaluation by the TAC. This is
   the nearest-term infrastructure change and needs practitioner
   input to resolve open questions around performance, scope, and
   composition semantics.

## Existing mechanisms in USD

Several existing mechanisms partially address units. Understanding
their capabilities and limitations is essential for designing the path
forward.

### Stage-level metrics metadata

USD provides three stage-level metadata fields related to units:

- **`metersPerUnit`** (`double`) -- declared in `UsdGeomLinearUnits`.
  Provides a scale factor from the stage's linear unit to meters.
  Default value is centimeters (`0.01`) for historical reasons.
- **`upAxis`** (`token`) -- declared in `UsdGeomTokens`. Specifies the
  stage's vertical axis (`Y` or `Z`).
- **`kilogramsPerUnit`** (`double`) -- declared by `UsdPhysics`.
  Provides a scale factor from the stage's mass unit to kilograms.

These metadata values live on the layer, not on prims. Under
composition, the strongest layer's metadata wins -- there is no
element-wise composition or reconciliation. When a layer with
`metersPerUnit = 0.01` is referenced into a stage with
`metersPerUnit = 1.0`, the stage's metadata value prevails, but no
geometry is adjusted. The mismatch is silent unless external tooling
detects it.

Critically, these metadata values describe only the *stage-level
convention*. They do not annotate individual attributes. A density
value on a physics prim has no declared unit dimension -- the system
cannot determine whether it should scale as length⁻³ or not at all.

Notably, the UsdPhysics schema *does* declare unit dimensions for its
attributes -- but only as human-readable doc strings, not as
machine-readable metadata. The schema consistently uses a `Units:`
convention: `Units: mass/distance/distance/distance` for density,
`Units: distance/second/second` for gravity, `Units: distance/second`
for velocity, `Units: mass*distance*distance` for inertia. This
information is precise, correct, and already maintained by the Physics
Working Group -- but it is trapped in prose. No tool can consume it
programmatically without string parsing. The intellectual work of
determining dimensional exponents has been done; the gap is purely one
of encoding: the same information expressed as structured metadata
(e.g., `customData` on attribute definitions) would be directly
consumable by conversion tools and validators.

### Time remapping vs. spatial remapping

USD provides `SdfLayerOffset` for automatic time remapping at
composition arc boundaries, but no equivalent for spatial units
(see [How USD handles units today](#how-usd-handles-units-today)).
The barrier to a spatial equivalent is that spatial attributes have
heterogeneous unit dimensions -- positions scale linearly, density
scales with length⁻³, gravity with length/time², light intensity
with length² -- and schemas do not declare which attributes are
unit-bearing or what their exponents are. Without that metadata,
any generic remapping layer would require an exhaustive rule table
that is always incomplete and drifts as schemas evolve.

### Metrics Assembler and Scene Optimizer

The Omniverse ecosystem provides two complementary tools for unit
correction, illustrating both what is possible today and where the
gaps remain:

**Metrics Assembler** (assembly-time, non-destructive) detects metric
mismatches when references or payloads are added and authors corrective
`xformOps` in a dedicated layer. It supports physics attribute
correction via registered rules, where resolution rules are
schema-driven: annotations in the physics schema define unit exponents,
and new attributes can be handled without code changes. Its core
library (USD dependency only) can be used to bake corrections
into a provided target layer. Limitations: it
operates only on references and payloads (not sublayers), requires
deep hierarchy traversal with performance cost at production scale,
and covers only transforms and a subset of physics attributes.

**Scene Optimizer's Edit Stage Metrics** (publish-time, destructive)
bakes the required scale into authored geometry, transforms, and
select schema attributes. Limitations: it operates only on the active
edit target (not referenced layers), does not recursively traverse
composition arcs, modifies vertices directly (which breaks mesh
sharing and conflicts with animation data in original local space),
and has specific failure modes when edit-layer overrides interact with
underlying composed transform stacks.

**Cross-layer unit consistency validation.** OpenUSD's validation
framework (`usdGeomValidators:StageMetadataChecker`) already checks
that `metersPerUnit` and `upAxis` are *authored*, but does not check
whether they are *consistent* across layers in a composed stage. A
validator that iterates the composed layer stack and flags divergent
`metersPerUnit` would be a natural addition to the framework.

Other ecosystems address unit reconciliation through different
mechanisms -- Unreal and Unity normalize to centimeters on import,
Houdini's DOPs assume MKS conventions, glTF mandates meters. These
demonstrate that the problem is solvable but that each system makes
different architectural tradeoffs. The Omniverse tools illustrate one
approach; the broader point is that the USD ecosystem lacks a
standardized, portable mechanism for unit reconciliation that works
across implementations.

## Industry use cases

The following examples illustrate the problem across industries. They
are not exhaustive but are intended to show that the need for unit
handling in composed scenes is broad and cross-cutting.

### Manufacturing and digital engineering

Manufacturing workflows assemble content spanning many orders of
magnitude in physical scale:

- An M3 screw (thread pitch 0.5 mm, head diameter 5.5 mm)
  mounted inside a CNC machine (working envelope ~1 m)
  in a factory building (footprint ~200 m)
  within a campus of factories (extent ~2 km)
  along a supply chain network (extent ~8,000 km)

At each level of this hierarchy, the smallest geometric detail that
must be preserved is different, the authoring tool likely used a
different unit system, and the stored coordinate values span many
orders of magnitude.

CAD systems (SolidWorks, Creo, NX) typically author in millimeters.
PLM systems (Teamcenter, Windchill) manage assets with
millimeter-scale geometry. When these assets enter a meter-scale USD
stage, every numeric value in every geometry attribute is 1,000x
larger than the stage expects. Corrective scaling at reference
boundaries addresses transforms, but does not cover physics constants
(gravity magnitude must change from `9.81` to `9810` in a
millimeter-scale stage), density values (which scale with length⁻³),
or velocity and force attributes.

Virtual factory stages assembling 2,000+ JT-sourced assets in
millimeters into a meter-scale stage have measured metrics resolution
times exceeding 80 seconds per reference path, with full stage-open
penalties reaching 90 seconds.

### Architecture, Engineering, Construction, and Operations (AECO)

AECO projects routinely mix metric and imperial units within a single
building model:

- A window frame (mullion width 50 mm) in a building facade
  (height ~40 m) on a campus (extent ~500 m) within a city-scale
  infrastructure model (extent ~50 km)

IFC, the open standard for building data exchange, defines geometry in
millimeters. Autodesk Revit uses feet internally (with user-facing
metric display). Archicad uses millimeters. When these models converge
in a USD stage for design review, visualization, or simulation, unit
mismatches are the norm, not the exception.

AECO workflows additionally face the challenge that many spatial
attributes are domain-specific: pipe diameters, duct cross-sections,
structural member dimensions, and clearance distances all carry
implicit unit assumptions from the originating tool. A unified
unit-handling mechanism must accommodate these without requiring
exhaustive domain-specific rules for every AECO attribute type.

### Robotics and simulation

Robotics simulation imposes the strictest requirements on unit
consistency:

- Physics engines require that gravity, mass, inertia, joint limits,
  and collision geometry all be expressed in consistent units.
  A 100x error in `metersPerUnit` produces a gravity constant that
  is 100x too strong or too weak, making simulation results
  physically meaningless.
- Robot descriptions (URDF, MJCF) typically use meters. Environments
  built from CAD data may use millimeters or centimeters. Assembling
  a robot into an environment without unit reconciliation produces
  a robot that is 1,000x too large or too small.
- Sensor simulation (LiDAR, cameras, contact sensors) depends on
  correct spatial relationships. Unit mismatches produce incorrect
  range measurements, field-of-view calculations, and collision
  detection results.

Unlike visual workflows where a scale error is merely distracting,
simulation failures due to unit mismatches are catastrophic, difficult
to diagnose, and can invalidate entire training runs or test campaigns.

### Media and Entertainment (M&E)

Even in USD's original domain, unit mismatches create practical
problems:

- DCC tools have different default unit systems. Maya defaults to
  centimeters, Houdini to meters, Blender to meters. Assets authored
  in different tools arrive at different scales.
- Camera and lighting workflows depend on correct spatial
  relationships. A camera's focal length is defined in "tenths of
  a scene unit" per the USD camera schema and should *not* be scaled
  when a global corrective scale is applied. Focus distance and
  clipping range *are* in scene units and must be scaled.
- Visual effects compositing integrates assets from multiple studios
  and vendors, each with their own unit conventions.

The M&E community has historically managed this through pipeline
conventions and artist discipline, but as scenes grow in complexity
and cross-studio collaboration increases, ad-hoc approaches become
increasingly problematic.

## Design considerations

This section outlines principles and open questions to guide the
community toward a solution. The goal is to establish consensus on the
problem structure and design principles before committing to a specific
mechanism -- not because a solution is distant, but because the current
landscape of fragmented approaches is a direct result of acting without
that consensus.

### Principles

1. **Separation of concerns.** Serialized units, working units, and
   display units are distinct layers of the problem. Solutions should
   address each layer independently. Display units are a UI concern.
   Working units are an application concern. Serialized units and
   their reconciliation at composition boundaries are the domain of
   this proposal.

2. **Non-destructive by default.** Solutions should preserve authored
   values wherever possible. Baking conversions into source data is
   acceptable as an explicit pipeline step, but should not be the only
   option. The correction mechanism should be auditable and reversible.

3. **Completeness over transforms.** Transform correction alone is
   insufficient. Any mechanism must be extensible to cover all
   unit-bearing attribute domains: physics (density, velocity, force,
   gravity), cameras (clipping range, focus distance), lights (spatial
   dimensions), and materials (displacement, subsurface scattering
   distances, volumetric density). The mechanism should not require
   exhaustive enumeration of every attribute, but should provide the
   metadata infrastructure for tools to determine the correct
   conversion for any unit-bearing attribute.

4. **Composability.** Unit metadata should participate in USD's
   composition model in a well-defined way. It should be clear what
   a prim's effective unit context is when it participates in
   references, inherits, specializations, and variant selections.
   Prim-level unit metadata (as proposed in the MetricsAPI direction)
   survives flattening and is discoverable per subtree, unlike
   layer-level metadata.

5. **Performance awareness.** Unit handling mechanisms must be
   evaluated against performance constraints at production scale.
   Deep hierarchy traversal for unit correction has been measured
   at 80+ seconds on factory-scale stages. Solutions should either
   reduce this cost (pre-computation, caching, evaluation-time
   resolution) or make it payable at a point in the pipeline where
   it does not block interactive workflows.

6. **Ecosystem agreement first.** The most impactful intervention
   requires no software changes: agreeing on canonical unit
   conventions. Conformant content eliminates the units problem
   entirely. Non-conformant content is explicitly identified and
   handled by whichever correction mechanism the pipeline employs.
   Software infrastructure should support and enforce the conventions
   the ecosystem agrees upon, not substitute for the agreement itself.

### Open questions and tradeoffs

The following questions are open within the Alliance for OpenUSD.
Each involves a real tradeoff -- there is no option without cost.
If you want to help, pick the one closest to your expertise
and bring concrete experience, not preferences.

1. **What are the canonical unit conventions?**
   This decision requires no changes to OpenUSD. Candidates include:

   - **SI base units** (meters, kilograms, seconds) -- natural for
     physics-based workflows and cross-industry interchange.
   - **Domain-specific conventions** -- millimeters for mechanical CAD,
     centimeters for game engines, feet for U.S. architectural practice.
   - **Declared but not prescribed** -- every asset must declare its
     units, but no single system is canonical.

   The IEDT and AECO Interest Groups represent the constituencies most
   affected. Convention agreement unblocks every subsequent
   infrastructure decision.

2. **Where should conversion happen, and who is responsible?**
   Where in the stack unit conversion occurs, and who bears the
   responsibility, are two facets of the same question. Six approaches
   span the spectrum:

   - **Standardize at the source.** Define canonical units and require
     conformance before content enters the system. Highest leverage --
     conformant content eliminates the problem. Cost: conformance
     burden on source authors and converters.
   - **Convert at ingest.** Detect divergence on upload and bake
     corrective scale into geometry and attributes; preserve originals
     alongside. Best runtime performance, but destructive to source
     data. Shared assets across pipelines with different targets
     require forking or variant strategies. A non-destructive variant
     of this approach writes converted values as **overs in a session
     sublayer**, leaving the source layer untouched -- the override
     layer can be removed to revert. This requires knowledge of
     dimensional exponents for every unit-bearing attribute (the same
     registry or schema metadata needed for assembly correction), but
     produces a stage where any consumer reads correct values with
     plain `attr.Get()` -- no unit-aware API needed downstream.
   - **Correct at assembly.** Author non-destructive corrective
     transforms at reference boundaries; source assets remain
     untouched. Good interactive UX, auditable and reversible. Cost
     scales with hierarchy depth; incomplete unless rules cover all
     unit-bearing domains.
   - **Pre-compute corrections.** Run assembly correction headlessly
     and cache results as static overlays. Pays the traversal cost
     once per asset change instead of once per stage open. Requires
     lifecycle management for stale overlays.
   - **Resolve at evaluation.** Make unit conversion part of value
     resolution -- convert after composition strength resolution,
     before consumers see the value. Cleanest long-term semantics,
     but requires unit-typed attributes, cache key management, and
     consistent adoption across all consumers. A multi-year ecosystem
     coordination effort.
   - **Scale at draw time.** Apply corrective scaling in the render
     delegate for read-only visualization. Zero composition cost,
     instant visual correctness. Does not fix authoring, physics,
     simulation, or export.

   The question is not which one to pick, but what the *default
   stack* should be and what each approach assumes about ecosystem
   agreement.

3. **Prim-level vs. layer-level unit metadata.**
   The Pixar proposal
   ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45),
   evaluated by the **TAC**) would move unit declarations from layer
   metadata to prim-level applied schemas (`UsdGeomMetricsAPI`,
   `UsdPhysicsMetricsAPI`), making units composable and discoverable
   at aggregation boundaries. The tradeoff: today, a validator can
   compare layer metadata without traversing the prim hierarchy --
   an early-exit path critical for authoring workflows that construct
   stages on the fly. Under the proposed encoding, detecting
   divergent units may require traversal, and querying applied API
   schemas at scale has
   [non-trivial cost](https://forum.aousd.org/t/proposal-to-revise-use-of-layer-metadata-in-usd/1422).
   If you run authoring or validation workflows at scale, this
   decision needs your data.

4. **Which attributes are unit-bearing, and what are their
   dimensional exponents?**
   The Geometry, Physics, and Materials Working Groups each own
   their domain's schemas, but no systematic audit exists. Density,
   gravity, velocity, displacement magnitude, SSS distances, texture
   physical scale, light intensity -- each needs a declared unit
   dimension before any conversion tool can handle it correctly.
   This is a cataloging problem. If you know your domain's
   unit-bearing attributes, that knowledge is directly useful --
   bring it to the relevant WG.

   Note that this concern is **orthogonal to MetricsAPI** (open
   question 3). MetricsAPI answers "what unit system is this subtree
   in?" -- the unit *context*. Dimensional exponents answer "how does
   this attribute scale with that context?" -- the conversion *rule*.
   Both are required to compute a correct conversion factor, but they
   are independent: MetricsAPI applies at the prim level and is the
   same for all attributes on a prim, while dimensional exponents are
   schema-level invariants (every `physics:density` is always
   M¹·L⁻³, regardless of which prim it appears on). As noted above,
   UsdPhysics already declares these exponents in doc strings -- the
   path forward is to formalize them as structured schema metadata,
   not to conflate them with prim-level unit declarations.

5. **How should unit-aware value resolution work?**
   A computational layer that resolves units during value evaluation
   (rather than requiring every consumer to re-implement conversion)
   is the long-term infrastructure goal. OpenExec (shipping with
   OpenUSD since v25.08) provides the execution framework for this:
   schema computations with automatic caching, invalidation, and
   multi-threaded evaluation. The community needs to scope this: is it
   feasible, what does it cost, and what subset of the problem does
   it actually cover? Default behavior must remain numeric-preserving
   for backward compatibility; unit-aware resolution is opt-in only.

6. **How should sublayer composition interact with units?**
   References and payloads provide natural boundaries where corrective
   transforms can be attached. Sublayers do not: their opinions
   compose directly into the root namespace with no single prim at
   which a correction can be applied. A sublayer with
   `metersPerUnit = 0.01` added to a `metersPerUnit = 1.0` stage
   contributes uncorrected numeric values across arbitrary prims.
   Should sublayer composition be considered out of scope for
   automatic unit handling? Or is infrastructure needed to detect
   and flag this case?

### Recommended baseline

Until the long-term infrastructure exists (unit-dimension annotations,
evaluation-time resolution), the recommended default stack is:

1. **Standardize at the source.** Define canonical units for your
   pipeline and enforce them through validation.
2. **Validate on ingest.** Reject or flag non-conforming content
   before it enters the assembly.
3. **Correct at assembly for what slips through.** Use non-destructive
   corrective transforms at reference boundaries as a safety net for
   content that arrives outside the standard.

This is not a complete solution -- it does not address derived
quantities, authored-value heterogeneity, or aggregation across
extreme scales. But it is implementable today with existing tools,
and it reduces the problem surface to the cases that genuinely require
the infrastructure work described above.

### Risks

1. **Paralysis by analysis.** The units problem has been discussed for
   years without resolution. The risk is that the community continues
   to debate the perfect long-term architecture while practitioners
   work around the problem with ad-hoc solutions that fragment the
   ecosystem further. The recommended baseline provides a
   pragmatic path forward that does not require waiting for
   infrastructure changes.

2. **Incomplete conversion coverage.** Any conversion mechanism that
   handles only transforms will produce silently wrong results for
   physics, cameras, lights, and materials. Practitioners will
   trust the mechanism and not verify. The risk is that partial
   solutions create false confidence. The design must make coverage
   gaps explicit and auditable.

3. **Performance at scale.** Deep hierarchy traversal for unit
   correction has significant cost at production scale. If the
   correction mechanism is in the interactive stage-open path, it
   becomes a blocking performance problem. Pre-computation and
   caching mitigate this but introduce lifecycle management
   complexity.

4. **Ecosystem fragmentation.** If the community cannot agree on
   canonical units, each pipeline will continue to enforce its own
   conventions, and cross-pipeline interoperability will remain
   broken. The infrastructure work (schemas, APIs, evaluation-time
   resolution) has value regardless, but its full benefit is
   realized only when combined with ecosystem-wide conventions.

5. **Backward compatibility.** Any change to how units are expressed
   or resolved must not break existing content or workflows. The
   current numeric-preserving composition model is a load-bearing
   guarantee. Unit-aware resolution must be opt-in, not default.

6. **Implementation-agnostic specification.** The attribute audit and
   any resulting unit-dimension annotations will flow to domain Working
   Groups (Physics, Geometry, Materials) for specification. Writing
   implementation-agnostic spec language for unit-bearing attributes is
   harder than it appears -- unit dimensions cross WG boundaries
   (density involves both physics and geometry, SSS distances involve
   materials and geometry), and WGs may default to implementation-specific
   language that ties the spec to a particular correction mechanism.
   Concrete examples of implementation-agnostic unit-dimension
   annotations should accompany any WG submission.

## Relationship to other proposals

This proposal connects to several related efforts in the OpenUSD
ecosystem:

- **[Revise Use of Layer Metadata](../revise_use_of_layer_metadata/README.md)**
  ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45))
  -- Proposes migrating stage metadata (including `metersPerUnit` and
  `upAxis`) to applied API schemas (`UsdGeomMetricsAPI`,
  `UsdPhysicsMetricsAPI`). This is the nearest-term infrastructure
  change directly relevant to units. The analysis in that proposal --
  that prim-level metadata survives flattening and is discoverable
  per subtree, unlike layer-level metadata -- is foundational to
  composable unit handling.

- **[Separation of Concerns for Identifiers](../identifier_separation_of_concerns/README.md)**
  -- Addresses a parallel problem: the distinction between USD
  namespace identifiers and external source identifiers. Both
  proposals share the theme of separating internal USD mechanisms
  from external system concerns, and both observe that conflating
  distinct roles leads to ad-hoc workarounds that fragment the
  ecosystem.

- **[Physical Lighting](../physical-lighting/README.md)** -- Light
  intensity behavior interacts with unit conventions: normalized
  lights divide by surface area expressed in meters². Stages with
  different `metersPerUnit` values produce different effective
  intensities. The units proposal's treatment of derived quantities
  (attributes that scale non-linearly with the unit ratio) applies
  directly to lighting.

- **[OpenExec](../openexec/README.md)** -- OpenExec's computation
  framework (shipping with OpenUSD since v25.08) is a natural fit for
  unit-aware value resolution. A schema computation registered on
  unit-bearing attributes could use OpenExec's `NamespaceAncestor`
  input accessor to walk up the hierarchy, find the nearest prim-level
  MetricsAPI declaration (the effective `metersPerUnit` context),
  compute the conversion factor, and return the value in canonical
  stage units -- the same pattern that `computeLocalToWorldTransform`
  uses to accumulate transforms through the hierarchy. Computed values
  would be automatically cached and invalidated when either the
  authored value or the metrics context changes. Key dependency:
  prim-level MetricsAPI
  ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45))
  must exist first to provide the per-prim unit context that the
  computation would consume. Limitation: tools that do not use
  OpenExec would not see converted values -- this is opt-in, not
  universal, and default behavior remains numeric-preserving.

## Next steps

1. **Submit as pull request.** Submit this proposal to the
   [OpenUSD-proposals](https://github.com/PixarAnimationStudios/OpenUSD-proposals)
   repository. Community feedback and discussion on the open questions
   is welcome there.

2. **Align on canonical conventions.** The most impactful near-term
   action requires no software changes. The IEDT Interest Group's
   charter explicitly includes "units and parameters requirements"
   with routing to the Core Specification Working Group -- this is an
   existing chartered mechanism for exactly this work. Convention
   agreement unblocks every subsequent infrastructure decision.

3. **Drive the MetricsAPI proposal forward.** The Pixar proposal
   ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45))
   is the nearest-term infrastructure change. It needs review from
   practitioners who will consume the resulting schemas -- especially
   those with authoring workflows that validate units during stage
   construction. Where competing approaches exist (prim-level vs.
   layer-level encoding, dictionary vs. schema), both should be
   implemented on representative workloads and measured before
   committing -- performance data from production-scale workflows
   resolves debates that opinions cannot.

4. **Conduct the attribute audit.** A systematic inventory of
   unit-bearing attributes across UsdGeom, UsdPhysics, UsdLux,
   UsdShade, and UsdGeomCamera is needed to establish the completeness
   scope for any conversion mechanism. The Geometry, Physics, and
   Materials Working Groups are the right venues for this work.
   UsdPhysics provides a head start: its schema already declares
   unit dimensions for every physics attribute via a consistent
   `Units:` doc-string convention. Formalizing these as structured,
   machine-readable metadata (rather than prose) is a concrete,
   low-risk first step that the Physics WG could undertake
   independently. The same approach should then be extended to
   UsdGeom, UsdLux, and UsdShade.

5. **Prototype evaluation-time resolution.** Based on alignment from
   steps 2--4, prototype an opt-in unit-aware value resolution API on
   a representative set of attributes, with measured performance
   overhead. This is a multi-year effort that benefits from early
   scoping.

Stakeholders who want to accelerate this work are encouraged to engage
directly on any of the steps above. The pace is determined by the
breadth of consensus achieved at each step -- and that consensus is
what ensures the solution serves the full community rather than a
single use case.

---

The units problem has persisted not because it is unsolvable, but
because it requires difficult decisions that cross organizational
boundaries. The path forward exists. It is not waiting for a
breakthrough -- it is waiting for the people who understand their
workflows, their tolerances, and their constraints to show up in the
forums where those decisions are being made and drive them to
conclusion. That means you.

## Appendix A: What conversion does not cover

Even when unit conversion is applied correctly at a composition
boundary, two categories of problems persist that routinely catch
practitioners off guard.

### Authored values under corrective transforms

When a corrective scale is applied at a reference or payload boundary,
everything *below* that boundary remains in the source asset's original
units. An author who writes `translate = 100` on a prim under an asset
originally encoded in centimeters (with a 0.01 corrective scale above
it) gets 1 m of world-space motion. The same `translate = 100` under an
asset encoded in meters produces 100 m of world-space motion.

This is not a bug -- it is a direct consequence of non-destructive
correction. But it means that identical authored values produce
different world-space results depending on which asset hierarchy they
live in. Animation curves, measurement tools, and property panels all
inherit this heterogeneity. Authors must inspect the transform stack to
predict the world-space effect of any edit.

This is arguably the hardest UX problem in the entire units story,
because it persists *after* assembly-time correction is working
correctly.

### Derived quantities require domain-specific rules

Spatial attributes -- positions, distances, extents -- scale linearly
with the unit ratio. But many attributes have unit dimensions that
involve powers of length, mass, or time:

- **Density** scales with length⁻³ (mass per unit volume).
- **Gravity** is a stage-level constant that must match the stage's
  linear units (9.81 m/s² becomes 981 cm/s²).
- **Velocity and force** scale with length/time and
  mass·length/time² respectively.
- **Light intensity per unit area** depends on the stage's linear
  unit squared.

Most conversion tools handle transforms only. Uncovered domains
produce silently wrong simulation, rendering, or measurement results.

The root cause is structural: most data schemas do not declare which
attributes are unit-bearing or what their unit dimensions are. Without
that annotation, conversion tools must maintain out-of-band rule
tables mapping attribute names to unit exponents -- tables that are
always incomplete and drift out of sync as schemas evolve. There is no
finite set that "completes" the conversion.

## Appendix B: AI-Assisted Drafting

This proposal was drafted with the assistance of an AI language model
(Claude, Anthropic) operating within Cursor IDE, under the direction of
Aaron Luk and Jens Jebens. All conceptual framing, editorial decisions,
and technical judgment are the responsibility of the human authors. The
AI was used as a drafting tool to accelerate the writing process based on
context and direction provided by the authors.

The context provided to the AI was itself the product of extensive
preceding work: stakeholder conversations, meeting transcripts, internal
Slack discussions, field observations from virtual factory deployments,
and review of the OpenUSD codebase, validation framework, and AOUSD
forum discussions. The AI did not participate in those
conversations; it received their outputs as input for drafting.

### Context provided to the AI

The following materials were gathered by the authors and provided as
input context. Each item represents human-directed research or
stakeholder engagement that preceded the drafting process:

1. **Stakeholder conversations and meeting transcripts** -- Sync
   meetings with domain experts covering factory-scale unit handling
   pain points, Metrics Assembler architecture, Kit default issues, and
   customer deployment experiences. Transcripts were reviewed and key
   findings extracted before being provided as context.

2. **Internal Slack threads and field observations** -- Practitioner
   reports on Metrics Assembler performance at scale, camera/light
   scaling semantics, and CAD converter limitations. Field observations
   from virtual factory deployments documenting where unit mismatches
   cause failures and what workarounds teams adopt.

3. **Technology-agnostic problem space analysis** -- A separate document
   analyzing the units problem across any aggregation system, covering
   serialized/working/display units, precision concerns, conversion
   architecture, derived quantities, and aggregation across scales.
   Developed over four multi-prompt sessions with human review and
   correction at each step.

4. **USD/Omniverse-specific analysis** -- A companion document covering
   Metrics Assembler and Scene Optimizer architecture, field
   observations, and an 8-step roadmap. Developed in parallel with the
   general analysis.

5. **User stories** -- Seven user stories covering the full units
   roadmap from spec/validation through SDK modules to OpenUSD ecosystem
   contributions. These defined the scope and acceptance criteria that
   the proposal addresses.

6. **OpenUSD codebase and validation framework** -- Direct review of the
   OpenUSD validation framework (`usdGeomValidators:StageMetadataChecker`)
   and the Omniverse Asset Validator (UN.001--UN.007) to understand what
   unit validation exists today and where the gaps are.

7. **OpenExec documentation and API reference** -- Research into
   OpenExec's computation framework (shipping with OpenUSD v25.08),
   including the `NamespaceAncestor` input accessor and its relevance to
   unit-aware value resolution.

8. **Existing proposals in this repository** -- The
   [Separation of Concerns for Identifiers](../identifier_separation_of_concerns/README.md)
   proposal was used as the primary structural reference.
   [Revise Use of Layer Metadata](../revise_use_of_layer_metadata/README.md)
   ([PR #45](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/45))
   was used as a key technical input on the MetricsAPI direction.

9. **AOUSD forum discussion** --
   [Forum thread](https://forum.aousd.org/t/proposal-to-revise-use-of-layer-metadata-in-usd/1422)
   on the MetricsAPI proposal, including performance concerns raised by
   practitioners.

### Review and refinement

The draft was refined through multiple rounds of review. Key editorial
decisions included:

- Merged "Key Questions" and "Solution Approaches" into a unified
  "Open questions and tradeoffs" section to eliminate repetition.
- Removed duplicate `SdfLayerOffset` discussion between Motivation and
  Existing Mechanisms.
- Expanded OpenExec from placeholder to substantive analysis
  (`NamespaceAncestor` accessor, MetricsAPI dependency, opt-in
  limitation).
- Added cross-layer unit consistency validation as a gap in both the
  OpenUSD validation framework and the Omniverse Asset Validator.
- Incorporated Metrics Assembler architecture details and schema-driven
  physics rules from developer input.
- Broadened Existing Mechanisms to reference non-Omniverse approaches
  (Unreal, Unity, Houdini, glTF).
- Removed partner and customer names.

A prompt-level drafting log for the problem space documents has been
archived separately.

## Appendix C: Units API Proof of Concept

A proof-of-concept Python library implementing the mechanisms described
in this proposal is available at:

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
        └── jjebens/units-aware-value-resolution  ← OpenExec + Hydra (Appendix D)
```

The Kit extension ([`jensjebens/omni-units-api`](https://github.com/jensjebens/omni-units-api))
vendors the Python POC and adds Kit-specific UI (Units Inspector window,
property widget annotations). It runs against stock USD (no fork
required).

## Appendix D: Evaluation-Time Unit Resolution — OpenExec and Hydra Integration

This appendix documents the proof-of-concept implementation of
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

5. **Performance overhead is negligible.** At 10,000 prims, unit-aware
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

1. **Stage-level metersPerUnit** is currently assumed to be 1.0
   (meters) in the OpenExec computation. The long-term solution is a
   stage-level computation via `Stage().Computation<double>` or
   `GeomMetricsAPI` applied to the stage root prim.

2. **upAxis Y↔Z rotation** is not yet implemented in the OpenExec
   computation (it was validated in the earlier Python POC).

3. **Camera, light, and physics attributes** beyond transforms are
   not yet covered by the Hydra integration but follow the same
   dimensional analysis pattern via the registry.

4. **Fabric population timing** in Kit requires deferred
   initialization (`ASSETS_LOADED` + one frame) because Fabric is
   not guaranteed to be populated at `StageEventType.OPENED` time.

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
