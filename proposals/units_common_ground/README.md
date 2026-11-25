# Units in OpenUSD: a common starting point

This document is the companion to the problem statement
[Units and Scale in Composed Scenes](../units_and_scale/README.md). The problem
statement provides the motivation and requirements; this document presents one
technical design against them.

The design takes Pixar's spatial metrics proposal (OpenUSD-proposals PR 114) as written
as step 1. Steps 2 to 4 add the requirements in the problem statement that PR 114 leaves
open. Step 5 is this draft's own suggestion for values that arrive in another unit. Each
step stands alone, keeps authored values as the only truth, and adds a validator for each
new way an asset can go wrong. A working prototype is in [`prototype/`](prototype/).

This draft has not been reviewed yet.

## Requirements this design addresses

**From [PR 114](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/114)**
(head 6266c1e), which this design keeps:

- Units on prims (`UsdSpatialMetricsAPI`), with the nearest ancestor that has the schema
  speaking for its subtree.
- Corrections written into the file as named transform ops, with a flag that separates a
  deliberate mismatch from a forgotten one, and validators that catch stale corrections.
- No evaluation-time conversion of geometry. OpenExec compensation was considered and
  not pursued, for two stated reasons: a computed correction handles only transforms, not
  attributes such as gravity, and authored corrections stay inspectable, can be validated,
  and work for clients that do not run OpenExec.
- Mass left as future work, planned as a separate `UsdPhysicsMetricsAPI`.

**From the [problem statement](../units_and_scale/README.md)**, which PR 114 leaves open:

- All seven SI base units (principle 9).
- One shared schema for the unit system, so that no domain has to own temperature.
- Composition rules written down for every arc before new schemas are built on top
  (open question 7).
- Each physics value can come from a different source in its own unit, while the solver
  computes in consistent units of its own choosing (open question 8).
- Exact conversion factors and enough precision for micrometre parts on metre boards
  (open question 9).

Two design choices need agreement:

- **One schema per domain, or one for all.** PR 114 lists a per-domain
  `UsdPhysicsMetricsAPI` as future work. Step 4 proposes one schema for the six base units
  other than length. Time, mass and temperature are shared by physics, thermal and electrical schemas, so per-domain schemas would either
  repeat them or make one domain own them. One schema gives a reviewer one place to look,
  one inheritance rule and one validator, which keeps the scene description easy to
  inspect, as PR 114 intends.
- **A unit on each property.** Some engineering simulation tools give each physics
  property its own unit, because each value comes from a different source. A property
  unit that overrides its subtree's gives one authored value two possible readings, which
  conflicts with principle 8 of the problem statement. Step 5 suggests a mechanism
  between the two.

## The proposal

### Step 1: PR 114 as written

`UsdSpatialMetricsAPI` (`spatial:metersPerUnit`, `spatial:upAxis`) and
`UsdGeomSpatialMetricsXformCompensationAPI`, with PR 114's inheritance rule, fallbacks,
backward compatibility and validators. This proposal changes none of it.

### Step 2: write down how units compose

The rule PR 114 already uses, applied to every arc: **units resolve on the composed
namespace; the nearest ancestor-or-self prim with the schema applied speaks for the
subtree.** What this means arc by arc:

| Arc | Effect on units | Validator |
|---|---|---|
| Reference, payload | The referenced prim keeps its units only if it carries the schema itself | PR 114 validator 2 |
| Relocate | A relocated prim takes its new parent's units unless it carries the schema itself | **CG-1** (new) |
| Inherits, specializes | A schema on a class reaches every prim that inherits it, in any asset | **CG-2** (new, warning) |
| Variants, sublayers | No special case: the composed opinion decides | none |
| Deactivation | The prim and its subtree leave the stage, so nothing is left to resolve | none |
| Instancing | Instance proxies resolve through the instance's ancestors | none |

Two further validators fill gaps that apply to PR 114 as well:

- **CG-3.** A prim with a units schema applied uses its own attribute values (PR 114,
  "Utility Methods", step 1), so an attribute that is not authored takes the schema
  fallback, not the ancestor's value. PR 114's own helper `ApplyAndAuthorUpAxis` creates
  this case: applied to a gripper under a robot in metres, it leaves the gripper's
  `spatial:metersPerUnit` at the fallback 0.01, and the gripper's lengths read as
  centimetres. PR 114 validator 3 reports a missing compensation, and adding one would
  shrink the gripper to match. CG-3 warns that the attribute is not authored (scenario
  S4b). The same applies to `UsdUnitSystemAPI` (scenario S4).
- **CG-4.** PR 114 validator 2, extended to the step 4 schema.

### Step 3: schemas declare the dimension of each attribute

A **dimension** is the kind of quantity an attribute holds: density is mass per length
cubed wherever it appears. It belongs to the schema that defines the attribute. Step 3
registers one attribute metadata field, `unitDimension`, as a dictionary of exponents
over the SI base dimensions (`L`, `M`, `T`, `I`, `Theta`, `N`, `J`):

```usda
double physics:density = 0 (
    unitDimension = {
        int L = -3
        int M = 1
    }
)
```

It must be a registered metadata field, not `customData`. usdGenSchema clears property
`customData` when it writes `generatedSchema.usda` (`usdGenSchema.py`, `GenerateRegistry`),
and keeps only the first sentence of the doc string as `userDocBrief`. That is why the
dimensions UsdPhysics already writes in its doc strings never reach a shipped build.
Running usdGenSchema from OpenUSD 26.8 on a test schema confirmed both halves:

- `unitDimension` came through unchanged.
- A `customData` entry on the same attribute was dropped.
- The doc string "Density. Units: mass/distance/distance/distance." became
  `userDocBrief = "Density."`.

At runtime, usd-core 26.8 returns the field through `UsdAttribute::GetMetadata` on any
prim that has the schema applied, with nothing authored on the prim.

This step changes no values and no behaviour. Custom attributes can carry the same
field.

UsdPhysics today:

- **25 attributes** have a `Units:` clause in `schema.usda`. The prototype turns them
  into a table (`prototype/tools/extract_physics_dimensions.py`).
- **7 of those 25 depend on the applied instance.** `PhysicsDriveAPI` and
  `PhysicsLimitAPI` are multiple-apply schemas, and their dimensions differ between
  linear and angular instances. For example, drive stiffness is M T⁻² for a linear drive
  and M L² T⁻² per degree for an angular one. One static field per attribute cannot
  express that. See the open questions.
- **6 numeric attributes have no clause.** Friction, restitution and gravity direction
  are dimensionless. `physics:localPos0` and `physics:localPos1` are lengths and say
  nothing. The field should be able to say "dimensionless" explicitly (`{}`).

### Step 4: one unit-system schema for the other six base units

`UsdUnitSystemAPI` replaces the per-domain `UsdPhysicsMetricsAPI` that PR 114 lists as
future work. It uses the same inheritance rule as `UsdSpatialMetricsAPI`:

| Attribute | Fallback |
|---|---|
| `units:kilogramsPerUnit` | 1 |
| `units:secondsPerUnit` | 1 |
| `units:amperesPerUnit` | 1 |
| `units:kelvinsPerUnit` | 1 |
| `units:molesPerUnit` | 1 |
| `units:candelasPerUnit` | 1 |

Length stays in `UsdSpatialMetricsAPI`, because it travels with up axis and drives the
compensation transform. Between them, the two schemas cover all seven SI base units.

**How non-spatial values are read.** Geometry needs a compensation transform because
every renderer reads points without asking about units. Physics, thermal and electrical
values are read by solvers, and a solver asks for its working units. With dimensions
declared (step 3) and units resolved (step 4), one utility in OpenUSD core gives the
conversion factor for any attribute, computed in double precision
([Appendix A](#appendix-a-unit-conversion-in-openusd-core)):

```
SI value = authored value × Π (factor of base b) ^ (exponent of b)
```

The authored value is never rewritten. The utility computes a factor on request, the
way `UsdGeomXformable::ComputeLocalToWorldTransform` computes a matrix, and changes
nothing on the stage. This is the "named multiplier that mass computations consume" idea from PR 114's
future-work section, generalised from mass to every declared quantity. It also covers
the case PR 114 leaves open: break force, drive stiffness and the other values no core
computation passes through.

### Step 5: values that arrive in another unit (this draft's suggestion)

This step is the draft's own suggestion, for a value that comes from a vendor catalogue, a sensor or an engineering standard in a unit
different from the asset's. The converter that writes the attribute (a CAD or simulation
converter, such as usd-convert-cad) converts it once into the prim's unit system and
records the source in the attribute's custom data:

```usda
float physics:density = 7850 (
    customData = {
        dictionary unitSource = {
            double value = 7.85
            string unit = "g/cm^3"
            double toSI = 1000
            double offsetToSI = 0
        }
    }
)
```

Readers only ever use `7850`. The record shows a reviewer where the number came from,
and **CG-5** fails when someone edits the value and leaves the record behind. The offset
lets Celsius and Fahrenheit source data be stored on the kelvin scale, so the unit system
itself needs factors only.

Under step 5 a property never carries a unit that overrides its subtree's: one value,
read one way. Where a group of values really does live in another unit system, it gets
its own prim with its own `UsdUnitSystemAPI`.

The alternative is a unit on each attribute, as metadata, overriding the
subtree's unit system. It keeps the source value as authored, needs no conversion in the
converter, and makes the `unitSource` record and CG-5 unnecessary. In exchange, a reader
checks two places to interpret every value. Which of the two to adopt is open
question 3 below.

## What it leaves out

- Display units, which belong to applications, as principle 1 of the problem statement
  sets out.
- Attribute types richer than a float: fields, expressions and time-varying quantities.
  The dimension field is what such types would build on.
- How a value scales apart from its unit, as with weld stiffness.
- Unit symbols and a syntax for them. Records like `unitSource.unit` are free text.

## Prototype

`prototype/` contains a codeless schema plugin with stand-ins for PR 114's two schemas,
`UnitSystemAPI`, an example `ThermalBodyAPI` that declares dimensions, and the
`unitDimension` field. It also has a Python resolver, a consumer-side reader, PR 114's
validators 1–4 and CG-1 to CG-5, and ten scenarios built from the concrete cases in the
problem statement and PR 114's own example. It runs on usd-core 26.8 with no build step.

```bash
python -m pytest prototype/scenarios/test_scenarios.py
python prototype/scenarios/demo.py
```

| # | Scenario | Result |
|---|---|---|
| S1 | Bolt (mm, Z-up) into factory (m, Y-up) | Uncompensated: PR114-3 twice. Compensated: clean, and still clean after flattening |
| S2 | Part in g and cm read by a solver in SI | density 7.85 → 7850 kg/m³, gravity 981 → 9.81 m/s², all through one generic conversion |
| S3 | Chip temperature from an 85 °C sensor | Stored as 358.15 on the kelvin scale with its source recorded; an attribute with no dimension makes the reader fail loudly |
| S4 | Gripper says grams, forgets milliseconds | CG-3 warning |
| S4b | Gripper authors only Z up with PR 114's schema | metersPerUnit falls back to 0.01; PR114-3 asks for a compensation, CG-3 names the unauthored attribute |
| S5 | Relocated gripper | CG-1 error; clean after the fixer applies the source units and a compensation |
| S6 | Class prim carries units | CG-2 lists the two prims it reaches |
| S7 | Vendor density, then edited by hand | Clean, then CG-5 error |
| S8 | Linear and angular drive stiffness | Converted correctly, but only through a naming rule on the instance |
| S9 | BGA in µm on a PCB in m, 0.2 m from the origin | PR 114's float3 compensation adds 5.6e-11 m error, less than the 2.9e-10 m from storing µm points as floats |

Precision is not a reason to change PR 114's compensation op to double:

- A float keeps about seven significant digits whatever the unit. Points are stored
  relative to their prim's own origin, so their absolute precision follows how far they
  reach from that origin.
- UsdGeom stores points as `point3f`. Under PR 114 each referenced asset keeps its points
  in its own units, the placement translate is `double3`, and USD composes the
  local-to-world transform in double (`GfMatrix4d`).
- PR 114 declares `xformOp:scale:metricsCompensation` as `float3`. The stored factor has
  the same relative precision as the points, so it adds at most about as much error as
  point storage already has. In S9 it adds 0.056 nm against 0.29 nm from the points.

In S9 the chip's points shift by at most 0.29 nm, more than three thousand times smaller
than a micrometre.

Precision depends on how far a prim's points reach from its own origin, not on the unit.
A `point3f` mesh with points 100 m from its origin resolves to steps of about 8 µm. An
asset that needs fine precision over a large extent has to be split into enough prims,
each with its points close to its own origin and placed by a double-precision transform.
That holds today, and neither PR 114 nor this draft changes it. No tolerance for a real
workflow has been stated yet, so whether some workflows need finer splitting than they
use today is open question 4.

## Open questions

1. Is a core conversion utility ([Appendix A](#appendix-a-unit-conversion-in-openusd-core))
   acceptable for non-spatial values in place of per-domain compensation
   schemas, and is its API right?
2. How should a multiple-apply schema declare dimensions that depend on the instance?
   The options are per-instance metadata, splitting linear and angular into separate
   schemas, or a naming rule like the prototype's.
3. For values that arrive in another unit: step 5's convert-and-record, or a unit on each
   attribute? If step 5, should `unitSource` records be standardised,
   or left to pipelines?
4. Are double-precision factors exact enough, and which conversions must be exact?
   Decimal factors such as 0.001 are not exactly representable in binary. The same
   discussion should set the position tolerances that real workflows need, and check them
   against `point3f` for the largest single meshes.
5. Should step 4 ship with all six attributes, or with mass alone at first, as the
   smallest change?

## Appendix A: unit conversion in OpenUSD core

Step 4 needs one implementation of the conversion maths, owned by OpenUSD. For spatial
units OpenUSD already owns it: `ComputeLocalToWorldTransform` composes every transform
in double (`GfMatrix4d`), so every consumer gets the same matrix. If each consumer wrote
its own conversion for mass, time, temperature or current, one might compute in float,
another might apply the exponents in a different order, and two tools could read
different numbers from the same attribute. Precision could not be checked across tools
that nobody controls, and the first goal of the draft, one interpretation per value,
would not hold.

The API below is a sketch; the names are illustrative.

```cpp
// Factor that converts the authored value of `attr` into the target unit system.
// Fails if the attribute declares no dimension (step 3).
static bool UsdUnitSystemAPI::ComputeConversionFactor(
    const UsdAttribute& attr,
    const UsdUnitSystemFactors& target,   // per base unit; SI by default
    double* factor);

// The attribute's value at `time`, converted into the target unit system.
// Scalars, vectors and arrays; computed and returned in double precision.
static bool UsdUnitSystemAPI::ComputeValueIn(
    const UsdAttribute& attr, UsdTimeCode time,
    const UsdUnitSystemFactors& target,
    VtValue* value);
```

Behaviour:

- **Dimension.** Read from the attribute's `unitDimension` (step 3). An attribute with no
  declared dimension fails; it never converts with a silent factor of 1. A declared
  empty dictionary (`{}`) is dimensionless and converts with factor 1.
- **Unit system.** Length from `UsdSpatialMetricsAPI`, the other six base units from
  `UsdUnitSystemAPI`, each resolved with the nearest-ancestor rule (steps 1, 2 and 4).
- **Maths.** `factor = Π (source factor of b / target factor of b) ^ (exponent of b)` over
  the seven base units, in double. Temperature is on the kelvin scale, so factors
  suffice; offsets appear only in step 5's source records.
- **No writes.** Both functions read the stage and change nothing on it.

Precision. The factor is a product of at most seven terms in double, so its relative
error is a few parts in 10^16. Most physics attributes are stored as `float`, which
already holds about 6 parts in 10^8. The stored value's own precision therefore
dominates, as `point3f` does for geometry, and the conversion adds nothing a consumer
can measure. Which factors must be exact is open question 4.

Instance-dependent dimensions (open question 2) have to be settled before
this API covers `PhysicsDriveAPI` and `PhysicsLimitAPI`.

The prototype implements the same maths in Python, in double precision
(`prototype/units_cg/convert.py`, `read_in`).

