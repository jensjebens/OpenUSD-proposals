# Units in OpenUSD: a common starting point

This document is the companion to the problem statement
[Units and Scale in Composed Scenes](../units_and_scale/README.md). The problem statement
describes the motivation and lists the requirements. This document presents one technical
design that meets those requirements.

Step 1 of the design is Pixar's spatial metrics proposal,
[OpenUSD-proposals PR 114](https://github.com/PixarAnimationStudios/OpenUSD-proposals/pull/114),
unchanged. Steps 2 to 4 meet the requirements in the problem statement that PR 114 leaves
open. Step 5 is a suggestion of this draft for values that come from a source in a
different unit from the asset. Each step can be adopted on its own. No step changes an
authored value, and every step adds a validator for the new errors that become possible
with that step. A working prototype is in [`prototype/`](prototype/).

This draft has not been reviewed yet.

## Requirements met by this design

PR 114 is itself a proposal, and none of it is part of OpenUSD yet. This design keeps
the following parts of PR 114, at head 6266c1e, unchanged:

- Under PR 114, an author declares the length unit and up axis of a prim by applying a schema,
  `UsdSpatialMetricsAPI`, to the prim. A prim without the schema takes the values from
  the nearest ancestor that has the schema applied.
- Under PR 114, when an asset is referenced into a stage with different units, a tool
  corrects the difference by authoring named transform ops on the referencing prim. A flag marks a
  deliberate difference that needs no correction, and validators report a correction
  that no longer matches the units on either side of the reference.
- Under PR 114, OpenUSD does not convert geometry at evaluation time. The authors of PR 114 considered
  computing the correction in OpenExec and did not pursue that approach, for two
  reasons. A computed correction
  applies only to transforms, so it cannot correct attributes such as gravity. An
  authored correction can be inspected and validated, and it also works for clients
  that do not run OpenExec.
- PR 114 lists mass as future work, for a separate schema, `UsdPhysicsMetricsAPI`.

PR 114 leaves the following requirements from the problem statement open. This design
meets them:

- The design declares all seven SI base units (principle 9).
- This design adds one schema, shared by every domain, that declares the unit system.
  Without a shared schema, a base unit
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
Step 4 of this design instead adds one new schema for the six base units other than
length. Physics,
thermal and electrical schemas all use time, mass and temperature, so per-domain schemas
would either declare those units several times or make the other domains depend on the
schema of one domain. With one schema, a reviewer looks in one place for the unit system of a prim,
and one inheritance rule and one validator apply.

The second choice is whether an attribute can declare its own unit. Some engineering
simulation tools give each physics property its own unit, because each value comes from
a different source. If an attribute could declare a unit that overrides the unit
system of the prim, the authored value would have two possible interpretations. Two
interpretations conflict with principle 8 of the problem statement, under which every
authored value has exactly one interpretation. This draft suggests a different
approach in step 5, in which a converter records the source value and the source unit
without giving the attribute a unit of its own.

## The proposal

### Step 1: PR 114 as written

Step 1 consists of the two schemas that PR 114 proposes, `UsdSpatialMetricsAPI`
(`spatial:metersPerUnit`, `spatial:upAxis`) and
`UsdGeomSpatialMetricsXformCompensationAPI`, with the inheritance rule, fallbacks,
backward compatibility and validators that PR 114 proposes for them. Neither schema is
part of OpenUSD yet. This proposal leaves all of PR 114 unchanged.

### Step 2: composition rules for units

Step 2 of this proposal applies the inheritance rule of PR 114 to every composition arc,
and adds validators for the arcs that need them. The rule is evaluated on the composed
stage. A prim that has the schema applied uses its own units.
Any other prim uses the units of the nearest ancestor that has the schema applied. The
table below lists the effect of each arc on units.

| Arc | Effect on units | Validator |
|---|---|---|
| Reference, payload | The referenced prim keeps its source units only if it has the schema applied itself | PR 114 validator 2 |
| Relocate | A relocated prim uses the units of its new parent unless it has the schema applied itself | **CG-1** (new) |
| Inherits, specializes | A schema applied to a class prim applies to every prim that inherits from it, in any asset | **CG-2** (new, warning) |
| Variants, sublayers | No special case: the strongest opinion on the composed stage determines the units | none |
| Deactivation | The prim and its subtree are removed from the composed stage, so their units do not matter | none |
| Instancing | Instance proxies use the units of the ancestors of the instance | none |

Validator 2 in PR 114 warns when a referenced prim does not have the schema applied
directly, because the prim then takes the units of the referencing stage and loses the
units of the source asset.

This proposal also adds two further validators, which report errors that can also occur
under PR 114:

- **CG-3** reports a units attribute that is not authored on a prim that has the schema
  applied. Such a prim uses its own attribute values (PR 114, "Utility Methods", step 1),
  so an attribute that is not authored takes the fallback value of the schema instead of
  the value from the prim's ancestor. The PR 114 helper `ApplyAndAuthorUpAxis` produces this case.
  Suppose a robot is authored in metres, and a tool uses the helper on the robot's
  gripper to set the gripper's up axis. The gripper's `spatial:metersPerUnit` then takes the
  fallback of 0.01, so the gripper's lengths are read as centimetres. PR 114 validator 3
  reports a missing compensation, and authoring that compensation would shrink the
  gripper a hundredfold. CG-3 reports the actual cause, which is the attribute that is
  not authored (scenario S4b). CG-3 applies to `UsdUnitSystemAPI` in the same way
  (scenario S4).
- **CG-4** applies PR 114 validator 2 to the schema from step 4.

### Step 3: dimensions declared in schemas

The physical dimension of a quantity is expressed by multiplying the base quantities
together, each raised to a specific power. Density, for example, has the dimension
mass × length⁻³, and velocity has the dimension length × time⁻¹. An attribute such as
`physics:density` has the same dimension in every asset, so the dimension belongs in the
schema that defines the attribute.

Step 3 adds a new attribute metadata field to OpenUSD, `unitDimension`, as a registered
metadata field. The value of
`unitDimension` is a dictionary that maps each SI base dimension (`L`, `M`, `T`, `I`,
`Theta`, `N`, `J`) to an exponent. Base dimensions with an exponent of zero are left out:

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
`userDocBrief`. For that reason, the units stated in the UsdPhysics doc strings are
missing from the generated schema. The prototype registers `unitDimension` through a plugin. A test schema run through
usdGenSchema from OpenUSD 26.8 with that plugin showed all three behaviours:

- `unitDimension` came through unchanged.
- A `customData` entry on the same attribute was dropped.
- The doc string "Density. Units: mass/distance/distance/distance." became
  `userDocBrief = "Density."`.

At runtime, `UsdAttribute::GetMetadata` in usd-core 26.8 returns the value of the
registered field from the schema definition for any prim that has the schema applied, without any
metadata authored on the prim.

This step changes no authored value and no behaviour. A custom attribute has no schema
definition, so the field can be authored on the attribute directly.

The doc strings of the UsdPhysics schemas already state units for most attributes:

- 25 attributes have a `Units:` clause in their doc strings in `schema.usda`. The
  prototype converts these clauses into a table of dimensions
  (`prototype/tools/extract_physics_dimensions.py`).
- For 7 of those 25 attributes, the dimension depends on the applied instance.
  `PhysicsDriveAPI` and `PhysicsLimitAPI` are multiple-apply schemas, and the dimensions
  of attributes in these schemas differ between linear and angular instances. For example, drive stiffness
  has the dimension M T⁻² for a linear drive and M L² T⁻² per degree for an angular one.
  A single static value per attribute cannot represent that difference. Open question 2
  asks how to handle it.
- Six numeric attributes have no `Units:` clause. Friction, restitution and gravity
  direction are dimensionless, and `physics:localPos0` and `physics:localPos1` are
  lengths. In the proposed field, an empty dictionary (`{}`) therefore declares an
  attribute dimensionless explicitly.

### Step 4: one unit-system schema for the other six base units

Step 4 adds a new schema, `UsdUnitSystemAPI`, which replaces the per-domain
`UsdPhysicsMetricsAPI` that PR 114 lists as future work. `UsdUnitSystemAPI` follows the
same inheritance rule as `UsdSpatialMetricsAPI`.

| Attribute | Fallback |
|---|---|
| `units:kilogramsPerUnit` | 1 |
| `units:secondsPerUnit` | 1 |
| `units:amperesPerUnit` | 1 |
| `units:kelvinsPerUnit` | 1 |
| `units:molesPerUnit` | 1 |
| `units:candelasPerUnit` | 1 |

Length stays in `UsdSpatialMetricsAPI`, together with up axis, because the compensation
transform uses both. Together, the two schemas declare all seven SI base units.

#### Conversion of non-spatial values

Geometry needs a compensation transform in the layer, because a renderer reads points
with no unit conversion. Physics, thermal and electrical values do not need a
compensation transform, because each solver requests values in the working units that
the solver uses. Step 4 therefore also adds a new
utility to OpenUSD core. Once each attribute declares its dimension (step 3) and the unit
system of each prim is resolved (step 4), the proposed utility computes the conversion
factor for any attribute in double precision
([Appendix A](#appendix-a-unit-conversion-in-openusd-core)):

```
SI value = authored value × Π (factor of base b) ^ (exponent of b)
```

The utility never rewrites the authored value. It computes a factor on request and
changes nothing on the stage, in the same way that the existing
`UsdGeomXformable::ComputeLocalToWorldTransform` computes a matrix. The future-work
section of PR 114 describes a named multiplier attribute that mass computations
consume, leaving authored values untouched. The utility generalises that idea from mass
to every attribute that declares a dimension. The utility also converts values such as
break force and drive stiffness. PR 114 leaves these values open, because OpenUSD core
has no computation that uses break force or drive stiffness.

### Step 5: values from a source in another unit (suggestion)

Some values come from a source in a different unit from the asset, for example a vendor
catalogue, a sensor or an engineering standard. Under step 5, the converter that
writes the attribute, for example the CAD converter usd-convert-cad, converts the value
once into the unit system of the prim. The converter also records the source value and
the source unit in a new `unitSource` dictionary in the custom data of the attribute:

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

Under step 5, no attribute has a unit that overrides the unit system of the prim, so
each authored value has one interpretation. Where a group of values is authored in
another unit system, those values belong on a separate prim that has `UsdUnitSystemAPI`
applied with that unit system.

The alternative is a unit on each attribute, authored as metadata, which overrides the
unit system of the prim. That approach keeps the source value as authored, needs no
conversion in the converter, and makes the `unitSource` record and CG-5 unnecessary. In
exchange, a reader has to check two places to interpret every value. Open question 3
asks which of the two approaches to adopt.

## Out of scope

- Display units are out of scope. Under principle 1 of the problem statement, display
  units are a concern of applications.
- Values that are not scalars or arrays are out of scope, for example fields,
  expressions and time-varying quantities. A later proposal for such values could use
  the dimension field from step 3.
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
  relative to the origin of the prim, so the absolute precision of a point depends on
  the distance of the point from that origin.
- UsdGeom stores points as `point3f`. Under PR 114, each referenced asset keeps its
  points in the units of the asset, the placement translate is `double3`, and USD composes the
  local-to-world transform in double (`GfMatrix4d`).
- PR 114 declares `xformOp:scale:metricsCompensation` as `float3`. The stored factor has
  the same relative precision as the points, so it adds at most about as much error as
  storing the points already does.

In S9, storing the chip's points as floats shifts them by at most 0.29 nm, which is more
than three thousand times smaller than a micrometre. The float compensation factor adds
at most a further 0.056 nm.

The precision of a mesh depends on the distance of the points from the origin of the
prim, and not on the unit of the mesh. A `point3f` mesh with points 100 m from the origin
resolves positions to steps of about 8 µm. An asset that needs fine precision over a
large extent therefore has to be split into enough prims. Each prim has points close to
the origin of that prim, and a double-precision transform places the prim. This
requirement already applies today, and neither PR 114 nor this draft changes the
requirement. No tolerance from a real workflow has been stated yet, so open question 4
asks whether some workflows need finer splitting than they use today.

## Open questions

1. Is the proposed conversion utility in OpenUSD core
   ([Appendix A](#appendix-a-unit-conversion-in-openusd-core)) acceptable for
   non-spatial values in place of per-domain compensation schemas, and is its API right?
2. How should a multiple-apply schema declare dimensions that depend on the instance?
   The options are per-instance metadata, separate schemas for linear and angular
   instances, or a naming rule like the one in the prototype.
3. Should values from a source in another unit be converted and recorded as in step 5,
   or should each attribute be able to declare its own unit? If step 5 is adopted,
   should `unitSource` records be standardised, or left to each pipeline?
4. Are double-precision factors exact enough, and which conversions must be exact?
   Decimal factors such as 0.001 are not exactly representable in binary. The same
   discussion should set the position tolerances that real workflows need, and check them
   against `point3f` for the largest single meshes.
5. Should step 4 ship with all six attributes, or with mass alone at first, as the
   smallest change?

## Appendix A: unit conversion in OpenUSD core

The conversion that step 4 proposes needs one implementation of the conversion maths,
maintained in OpenUSD. For spatial units, OpenUSD already has one: `ComputeLocalToWorldTransform` composes every
transform in double (`GfMatrix4d`), so every consumer gets the same matrix. If each
consumer wrote its own conversion for mass, time, temperature or current, one consumer
might compute in float, and another might apply the exponents in a different order. Two
tools could then read different numbers from the same attribute. The precision of the
conversion could not be checked across independent tools, and principle 8 of the problem
statement, that every authored value has exactly one interpretation, would not hold.

The API below is a sketch of the two proposed functions, and the names are
illustrative.

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
  (`{}`) is dimensionless, and the value of the attribute is converted with a factor
  of 1.
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
this API can convert the attributes of `PhysicsDriveAPI` and `PhysicsLimitAPI`.

The prototype implements the same maths in Python, in double precision
(`read_in` in `prototype/units_cg/convert.py`).
