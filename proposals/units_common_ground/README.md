# Units in OpenUSD: a common starting point

This document is the companion to the problem statement
[Units and Scale in Composed Scenes](../units_and_scale/README.md). The problem statement
sets out the motivation and the requirements, and this document presents one technical
design that meets them.

The design adopts Pixar's spatial metrics proposal,
[OpenUSD-proposals PR 114](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/114),
unchanged as step 1. Steps 2 to 4 meet the requirements in the problem statement that
PR 114 does not address. Step 5 is a suggestion of this draft for values whose source
uses a different unit from the asset. Each step can be adopted on its own, none of them
changes an authored value, and each adds a validator for the new errors that it makes
possible. A working prototype is in [`prototype/`](prototype/).

This draft has not been reviewed yet.

## Requirements this design addresses

The design keeps the following parts of PR 114, at head 6266c1e:

- A prim declares its length unit and up axis by applying a schema,
  `UsdSpatialMetricsAPI`. A prim without the schema uses the values of its nearest
  ancestor that has the schema applied.
- When an asset is referenced into a stage with different units, a tool corrects the
  difference by authoring named transform ops on the referencing prim. A flag marks a
  deliberate difference that needs no correction, and validators report a correction
  that no longer matches the units on either side of the reference.
- OpenUSD does not convert geometry at evaluation time. PR 114 considered computing the
  correction in OpenExec and did not pursue it, for two reasons. A computed correction
  applies only to transforms, so it cannot correct attributes such as gravity. An
  authored correction can be inspected and validated, and it also works for clients
  that do not run OpenExec.
- PR 114 defers mass to future work, in a separate schema, `UsdPhysicsMetricsAPI`.

The design also meets the following requirements in the problem statement, which PR 114
does not address:

- The design covers all seven SI base units (principle 9).
- One schema, shared by every domain, declares the unit system. Without it, a base unit
  that several domains use, such as temperature, would be declared in the schema of one
  domain and used from the others (point 6 under "Why this matters now").
- The rules for units are written down for every composition arc before new schemas
  build on them (open question 7).
- Each physics value can come from a different source, in the unit of that source,
  while a solver computes in consistent units of its own choosing (open question 8).
- Conversion factors are exact enough, and precision is sufficient for parts authored
  in micrometres on boards authored in metres (open question 9).

### Two design choices that need agreement

The first choice is between a separate unit schema for each domain and one unit schema
shared by all domains. PR 114 lists a per-domain `UsdPhysicsMetricsAPI` as future work.
Step 4 proposes instead one schema for the six base units other than length. Physics,
thermal and electrical schemas all use time, mass and temperature, so per-domain schemas
would either declare those units several times or make the other domains depend on one
of them. With one schema, a reviewer looks in one place for the unit system of a prim,
and one inheritance rule and one validator apply.

The second choice is whether an attribute can declare its own unit. Some engineering
simulation tools give each physics property its own unit, because each value comes from
a different source. If an attribute's unit overrides the unit system of its subtree,
one authored value has two possible interpretations, which conflicts with principle 8
of the problem statement. Step 5 suggests a way to keep a record of the source value and
its unit without giving the attribute a unit of its own.

## The proposal

### Step 1: PR 114 as written

Step 1 adopts `UsdSpatialMetricsAPI` (`spatial:metersPerUnit`, `spatial:upAxis`) and
`UsdGeomSpatialMetricsXformCompensationAPI`, with the inheritance rule, fallbacks,
backward compatibility and validators of PR 114. This proposal changes none of them.

### Step 2: composition rules for units

Step 2 applies the inheritance rule of PR 114 to every composition arc. The rule is
evaluated on the composed stage. A prim uses its own units if it has the schema applied,
and otherwise the units of its nearest ancestor that has the schema applied. The table
below gives the effect of each arc.

| Arc | Effect on units | Validator |
|---|---|---|
| Reference, payload | The referenced prim keeps its source units only if it has the schema applied itself | PR 114 validator 2 |
| Relocate | A relocated prim uses the units of its new parent unless it has the schema applied itself | **CG-1** (new) |
| Inherits, specializes | A schema applied to a class prim applies to every prim that inherits from it, in any asset | **CG-2** (new, warning) |
| Variants, sublayers | No special case: the strongest opinion on the composed stage determines the units | none |
| Deactivation | The prim and its subtree are removed from the composed stage, so their units do not matter | none |
| Instancing | Instance proxies use the units of the ancestors of the instance | none |

PR 114 validator 2 warns when a referenced prim does not have the schema applied
directly, because the prim then takes its units from the referencing stage and loses
the units of its source.

Two further validators cover errors that are also possible under PR 114:

- **CG-3** reports a units attribute that is not authored on a prim that has the schema
  applied. Such a prim uses its own attribute values (PR 114, "Utility Methods", step 1),
  so an attribute that is not authored takes the fallback value of the schema instead of
  the value of its ancestor. The PR 114 helper `ApplyAndAuthorUpAxis` produces this case.
  Suppose a robot is authored in metres, and a tool uses the helper on the robot's
  gripper to set its up axis. The gripper's `spatial:metersPerUnit` then takes the
  fallback of 0.01, so the gripper's lengths are read as centimetres. PR 114 validator 3
  reports a missing compensation, and authoring that compensation would shrink the
  gripper a hundredfold. CG-3 reports the actual cause, which is the attribute that is
  not authored (scenario S4b). CG-3 applies to `UsdUnitSystemAPI` in the same way
  (scenario S4).
- **CG-4** applies PR 114 validator 2 to the schema from step 4.

### Step 3: dimensions declared in schemas

The physical dimension of a quantity expresses it in terms of the base quantities, as a
product of their powers. Density, for example, has the dimension mass × length⁻³, and
velocity has the dimension length × time⁻¹. An attribute such as `physics:density` has
the same dimension in every asset, so its dimension belongs in the schema that defines
the attribute.

Step 3 registers one attribute metadata field, `unitDimension`. Its value is a
dictionary that maps each SI base dimension (`L`, `M`, `T`, `I`, `Theta`, `N`, `J`) to
its exponent. Base dimensions with an exponent of zero are left out:

```usda
double physics:density = 0 (
    unitDimension = {
        int L = -3
        int M = 1
    }
)
```

The field has to be registered metadata, because usdGenSchema keeps registered
metadata fields and drops property `customData`. When usdGenSchema writes
`generatedSchema.usda`, it clears `customData` on each property (`usdGenSchema.py`,
`GenerateRegistry`), and it keeps only the first sentence of each doc string, as
`userDocBrief`. For that reason, the units that UsdPhysics states in its doc strings are
missing from the generated schema. A test schema run through usdGenSchema from OpenUSD
26.8 showed all three behaviours:

- `unitDimension` came through unchanged.
- A `customData` entry on the same attribute was dropped.
- The doc string "Density. Units: mass/distance/distance/distance." became
  `userDocBrief = "Density."`.

At runtime, `UsdAttribute::GetMetadata` in usd-core 26.8 returns the value of the field
from the schema definition for any prim that has the schema applied, without any
metadata authored on the prim.

This step changes no authored value and no behaviour. A custom attribute has no schema
definition, so the field can be authored on the attribute directly.

The UsdPhysics schemas already state units for most of their attributes, in their doc
strings:

- 25 attributes have a `Units:` clause in their doc strings in `schema.usda`. The
  prototype converts these clauses into a table of dimensions
  (`prototype/tools/extract_physics_dimensions.py`).
- For 7 of those 25 attributes, the dimension depends on the applied instance.
  `PhysicsDriveAPI` and `PhysicsLimitAPI` are multiple-apply schemas, and their
  dimensions differ between linear and angular instances. For example, drive stiffness
  has the dimension M T⁻² for a linear drive and M L² T⁻² per degree for an angular one.
  One static field per attribute cannot express that difference, which open question 2
  raises.
- Six numeric attributes have no `Units:` clause. Friction, restitution and gravity
  direction are dimensionless, and `physics:localPos0` and `physics:localPos1` are
  lengths. The field therefore has to be able to declare an attribute dimensionless
  explicitly, with an empty dictionary (`{}`).

### Step 4: one unit-system schema for the other six base units

Step 4 adds `UsdUnitSystemAPI` in place of the per-domain `UsdPhysicsMetricsAPI` that
PR 114 lists as future work. It uses the same inheritance rule as
`UsdSpatialMetricsAPI`.

| Attribute | Fallback |
|---|---|
| `units:kilogramsPerUnit` | 1 |
| `units:secondsPerUnit` | 1 |
| `units:amperesPerUnit` | 1 |
| `units:kelvinsPerUnit` | 1 |
| `units:molesPerUnit` | 1 |
| `units:candelasPerUnit` | 1 |

Length stays in `UsdSpatialMetricsAPI`, together with up axis, because the compensation
transform uses both. Together, the two schemas cover all seven SI base units.

#### Conversion of non-spatial values

Geometry needs a compensation transform in the layer, because a renderer reads points
with no unit conversion. Physics, thermal and electrical values do not need one, because
a solver requests them in its own working units. Once each attribute declares its
dimension (step 3) and the unit system of each prim is resolved (step 4), one utility in
OpenUSD core can compute the conversion factor for any attribute in double precision
([Appendix A](#appendix-a-unit-conversion-in-openusd-core)):

```
SI value = authored value × Π (factor of base b) ^ (exponent of b)
```

The utility never rewrites the authored value. It computes a factor on request and
changes nothing on the stage, in the same way that
`UsdGeomXformable::ComputeLocalToWorldTransform` computes a matrix. The future-work
section of PR 114 describes a named multiplier attribute that mass computations
consume, leaving authored values untouched. The utility generalises that idea from mass
to every attribute that declares a dimension. It also converts the values that PR 114
leaves open because no computation in OpenUSD core uses them, such as break force and
drive stiffness.

### Step 5: values whose source uses another unit (this draft's suggestion)

Some values come from a source that uses a different unit from the asset, for example a
vendor catalogue, a sensor or an engineering standard. Under step 5, the converter that
writes the attribute, for example the CAD converter usd-convert-cad, converts the value
once into the unit system of the prim. The converter also records the source value and
its unit in the custom data of the attribute:

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

Tools read only the authored value, 7850. The record shows a reviewer where the number
came from, and a new validator, **CG-5**, reports an error when someone edits the value
and leaves the record unchanged. The offset allows source data in degrees Celsius or
Fahrenheit to be authored on the kelvin scale, so the unit system itself needs only
factors.

Under step 5, no attribute has a unit that overrides the unit system of its subtree, so
each authored value has one interpretation. Where a group of values is authored in
another unit system, those values belong on their own prim, with its own
`UsdUnitSystemAPI`.

The alternative is a unit on each attribute, authored as metadata, which overrides the
unit system of the subtree. That approach keeps the source value as authored, needs no
conversion in the converter, and makes the `unitSource` record and CG-5 unnecessary. In
exchange, a reader has to check two places to interpret every value. Open question 3
asks which of the two approaches to adopt.

## Out of scope

- Display units are out of scope, because they belong to applications, as principle 1
  of the problem statement sets out.
- Values that are not scalars or arrays are out of scope, for example fields,
  expressions and time-varying quantities. Such values would build on the dimension
  field from step 3.
- Values that scale independently of their unit, such as weld stiffness, are out of
  scope.
- Unit symbols, and a syntax for them, are out of scope. Records such as
  `unitSource.unit` hold free text.

## Prototype

The prototype in `prototype/` contains a codeless schema plugin with stand-ins for the two
PR 114 schemas, `UnitSystemAPI`, an example `ThermalBodyAPI` that declares dimensions,
and the `unitDimension` field. It also contains a Python resolver, a reader that converts
values into the units that a consumer requests, PR 114 validators 1 to 4, and CG-1 to
CG-5. Ten scenarios are built from the concrete cases in the problem statement and from
the PR 114 example. The prototype runs on usd-core 26.8 with no build step.

```bash
python -m pytest prototype/scenarios/test_scenarios.py
python prototype/scenarios/demo.py
```

| # | Scenario | Result |
|---|---|---|
| S1 | Bolt (mm, Z-up) into factory (m, Y-up) | Uncompensated: PR114-3 twice. Compensated: clean, and still clean after flattening |
| S2 | Part in g and cm read by a solver in SI | Density 7.85 → 7850 kg/m³ and gravity 981 → 9.81 m/s², both through one generic conversion |
| S3 | Chip temperature from an 85 °C sensor | Authored as 358.15 on the kelvin scale with its source recorded; the reader raises an error on an attribute with no declared dimension |
| S4 | Gripper authors grams but not milliseconds | CG-3 warning |
| S4b | Gripper authors only Z up with the PR 114 schema | metersPerUnit falls back to 0.01; PR114-3 reports a missing compensation, CG-3 names the attribute that is not authored |
| S5 | Relocated gripper | CG-1 error; clean after the fix authors the source units and a compensation |
| S6 | Class prim with units applied | CG-2 lists the two prims that inherit from it |
| S7 | Vendor density, then edited by hand | Clean, then CG-5 error |
| S8 | Linear and angular drive stiffness | Converted correctly, but only through a naming rule on the instance |
| S9 | BGA in µm on a PCB in m, 0.2 m from the origin | The float3 compensation from PR 114 adds 5.6e-11 m of error, less than the 2.9e-10 m from storing µm points as floats |

### Precision

The compensation op in PR 114 does not need to be changed to double, for three reasons:

- A float keeps about seven significant digits, whatever the unit. Points are stored
  relative to the origin of their own prim, so their absolute precision depends on how
  far they extend from that origin.
- UsdGeom stores points as `point3f`. Under PR 114, each referenced asset keeps its
  points in its own units, the placement translate is `double3`, and USD composes the
  local-to-world transform in double (`GfMatrix4d`).
- PR 114 declares `xformOp:scale:metricsCompensation` as `float3`. The stored factor has
  the same relative precision as the points, so it adds at most about as much error as
  storing the points already does.

In S9, storing the chip's points as floats shifts them by at most 0.29 nm, which is more
than three thousand times smaller than a micrometre. The float compensation factor adds
at most a further 0.056 nm.

The precision of a mesh depends on how far its points extend from the origin of its
prim, and not on its unit. A `point3f` mesh with points 100 m from its origin resolves
positions to steps of about 8 µm. An asset that needs fine precision over a large extent
therefore has to be split into enough prims, each with its points close to its own
origin and placed by a double-precision transform. That is already true today, and
neither PR 114 nor this draft changes it. No real workflow has stated a tolerance yet,
so open question 4 asks whether some workflows need finer splitting than they use today.

## Open questions

1. Is a conversion utility in OpenUSD core
   ([Appendix A](#appendix-a-unit-conversion-in-openusd-core)) acceptable for
   non-spatial values in place of per-domain compensation schemas, and is its API right?
2. How should a multiple-apply schema declare dimensions that depend on the instance?
   The options are per-instance metadata, separate schemas for linear and angular
   instances, or a naming rule like the one in the prototype.
3. Should values whose source uses another unit be converted and recorded as in step 5,
   or should each attribute be able to declare its own unit? If step 5 is adopted,
   should `unitSource` records be standardised, or left to each pipeline?
4. Are double-precision factors exact enough, and which conversions must be exact?
   Decimal factors such as 0.001 are not exactly representable in binary. The same
   discussion should set the position tolerances that real workflows need, and check them
   against `point3f` for the largest single meshes.
5. Should step 4 ship with all six attributes, or with mass alone at first, as the
   smallest change?

## Appendix A: unit conversion in OpenUSD core

Step 4 needs one implementation of the conversion maths, maintained in OpenUSD. For
spatial units, OpenUSD already has one: `ComputeLocalToWorldTransform` composes every
transform in double (`GfMatrix4d`), so every consumer gets the same matrix. If each
consumer wrote its own conversion for mass, time, temperature or current, one consumer
might compute in float, and another might apply the exponents in a different order. Two
tools could then read different numbers from the same attribute. The precision of the
conversion could not be checked across independent tools, and principle 8 of the problem
statement, that every authored value has exactly one interpretation, would not hold.

The API below is a sketch, and the names are illustrative.

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

Both functions behave as follows:

- They read the dimension from the `unitDimension` field of the attribute (step 3). If
  the attribute declares no dimension, both functions fail, so a value is never
  converted with a silent factor of 1. An attribute that declares an empty dictionary
  (`{}`) is dimensionless, and it converts with a factor of 1.
- They take the length unit from `UsdSpatialMetricsAPI` and the other six base units
  from `UsdUnitSystemAPI`, each resolved with the nearest-ancestor rule (steps 1, 2
  and 4).
- They compute `factor = Π (source factor of b / target factor of b) ^ (exponent of b)`
  over the seven base units, in double. Temperature is on the kelvin scale, so factors
  are sufficient, and offsets appear only in the source records of step 5.
- They read the stage and author nothing on it.

The conversion adds no measurable error. The factor is a product of at most seven terms
in double, so its relative error is a few parts in 10^16. Most physics attributes are
stored as `float`, which already has a relative error of about 6 parts in 10^8. The
precision of the stored value therefore dominates, as `point3f` does for geometry. Open
question 4 asks which factors must be exact.

The dimensions that depend on the instance (open question 2) have to be settled before
this API covers `PhysicsDriveAPI` and `PhysicsLimitAPI`.

The prototype implements the same maths in Python, in double precision
(`read_in` in `prototype/units_cg/convert.py`).
