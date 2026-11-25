"""What kind of quantity an attribute holds.

Lookup order:
1. `unitDimension` metadata. For a schema attribute this comes from the schema
   definition (a registered metadata field survives usdGenSchema); for a custom
   attribute it is authored on the attribute.
2. Transitional table recovered from UsdPhysics' "Units:" doc strings, until UsdPhysics
   declares `unitDimension` itself.

A dimension is a dict of exponents over L, M, T, I, Theta, N, J. 'angle' may appear:
angles are dimensionless in SI, and UsdPhysics fixes them to degrees, so no unit system
scales them.
"""
import json
import os

_TABLE = None


def _physics_table():
    global _TABLE
    if _TABLE is None:
        here = os.path.dirname(__file__)
        with open(os.path.join(here, "usdphysics_dimensions.json")) as f:
            _TABLE = json.load(f)
    return _TABLE


def _instance_kind(instance):
    if instance.startswith(("trans", "linear", "distance")):
        return "linear"
    if instance.startswith(("rot", "angular")):
        return "angular"
    return None


def _physics_dimension(attr):
    prim = attr.GetPrim()
    name = attr.GetName()
    table = _physics_table()
    # Multiple-apply schemas: limit:<instance>:physics:low, drive:<instance>:physics:stiffness
    parts = name.split(":")
    if parts[0] in ("limit", "drive") and len(parts) >= 4:
        schema = "PhysicsLimitAPI" if parts[0] == "limit" else "PhysicsDriveAPI"
        entry = table.get(f"{schema}.{':'.join(parts[2:])}")
        kind = _instance_kind(parts[1])
        return entry.get(kind) if entry and kind else None
    candidates = [prim.GetTypeName()] + list(prim.GetAppliedSchemas())
    # Joint subclasses inherit PhysicsJoint's attributes.
    if prim.GetTypeName().startswith("Physics") and prim.GetTypeName().endswith("Joint"):
        candidates.append("PhysicsJoint")
    for schema in candidates:
        entry = table.get(f"{schema}.{name}")
        if entry and "dimension" in entry:
            return entry["dimension"]
    return None


def get_dimension(attr):
    """Exponent dict, {} for a declared dimensionless quantity, None if unknown."""
    dim = attr.GetMetadata("unitDimension")
    if dim is not None:
        return dict(dim)
    return _physics_dimension(attr)


def factor(dimension, system):
    """SI value of one authored unit of this dimension under `system` (from unit_system)."""
    f = 1.0
    for base, exp in dimension.items():
        if base == "angle":
            continue
        f *= system[base] ** exp
    return f


def format_dimension(dimension):
    if not dimension:
        return "dimensionless"
    return " ".join(f"{b}^{e}" if e != 1 else b for b, e in sorted(dimension.items()))
