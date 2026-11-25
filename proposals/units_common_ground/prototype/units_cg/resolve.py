"""Effective units for a prim.

One rule for every base unit, copied from PR 114's UsdSpatialMetricsAPI: the nearest
ancestor-or-self prim with the schema applied is authoritative for its subtree, and an
unauthored attribute on that prim takes the schema fallback. Length and up axis come
from SpatialMetricsAPI (PR 114, unchanged); the other six SI base units come from
UnitSystemAPI.
"""
from pxr import Usd, UsdGeom

SPATIAL = "SpatialMetricsAPI"
UNITS = "UnitSystemAPI"

# Base dimension -> (schema, attribute). Symbols follow the SI brochure.
BASE = {
    "L": (SPATIAL, "spatial:metersPerUnit"),
    "M": (UNITS, "units:kilogramsPerUnit"),
    "T": (UNITS, "units:secondsPerUnit"),
    "I": (UNITS, "units:amperesPerUnit"),
    "Theta": (UNITS, "units:kelvinsPerUnit"),
    "N": (UNITS, "units:molesPerUnit"),
    "J": (UNITS, "units:candelasPerUnit"),
}
UP_AXIS = (SPATIAL, "spatial:upAxis")


def governing_prim(prim, schema):
    """Nearest ancestor-or-self with `schema` applied, or None."""
    p = prim
    while p and not p.IsPseudoRoot():
        if p.HasAPI(schema):
            return p
        p = p.GetParent()
    return None


def _fallback(schema, attr):
    d = Usd.SchemaRegistry().FindAppliedAPIPrimDefinition(schema)
    return d.GetAttributeFallbackValue(attr)


def compute_effective(prim, base):
    """(value, governing prim path or None) for one base dimension or 'upAxis'."""
    schema, attr = UP_AXIS if base == "upAxis" else BASE[base]
    gov = governing_prim(prim, schema)
    if gov:
        return gov.GetAttribute(attr).Get(), gov.GetPath()
    stage = prim.GetStage()
    # PR 114 backward compatibility: layer metadata, then the schema fallback.
    if base == "L" and UsdGeom.StageHasAuthoredMetersPerUnit(stage):
        return UsdGeom.GetStageMetersPerUnit(stage), None
    if base == "upAxis" and stage.HasAuthoredMetadata("upAxis"):
        return UsdGeom.GetStageUpAxis(stage), None
    return _fallback(schema, attr), None


def unit_system(prim):
    """All seven SI factors for `prim`: {'L': metersPerUnit, 'M': kilogramsPerUnit, ...}."""
    return {b: compute_effective(prim, b)[0] for b in BASE}


def parent_context(prim):
    """Effective units the prim would have without its own schemas (its parent's)."""
    parent = prim.GetParent()
    out = unit_system(parent)
    out["upAxis"] = compute_effective(parent, "upAxis")[0]
    return out
