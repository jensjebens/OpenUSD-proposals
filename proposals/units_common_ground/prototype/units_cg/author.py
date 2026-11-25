"""Authoring helpers.

- `apply_units`: apply SpatialMetricsAPI / UnitSystemAPI and author the given factors.
- `compensate_spatial`: PR 114's CompensateSpatialMetrics, unchanged in intent.
- `author_from_source`: convert a value from its source unit into the prim's unit system
  at authoring time and keep the source as a record. The authored value is the only one
  any reader uses; the record exists so a reviewer can see where the number came from
  and a validator can tell when it goes stale.
"""
from pxr import UsdGeom

from .dimensions import factor, get_dimension
from .resolve import BASE, SPATIAL, UNITS, compute_effective, unit_system

COMP = "SpatialMetricsXformCompensationAPI"


def apply_units(prim, upAxis=None, **factors):
    """apply_units(prim, L=0.001, M=0.001, upAxis='Z') authors only what is given."""
    spatial = {k: v for k, v in factors.items() if BASE[k][0] == SPATIAL}
    other = {k: v for k, v in factors.items() if BASE[k][0] == UNITS}
    if spatial or upAxis:
        prim.ApplyAPI(SPATIAL)
        for k, v in spatial.items():
            prim.GetAttribute(BASE[k][1]).Set(v)
        if upAxis:
            prim.GetAttribute("spatial:upAxis").Set(upAxis)
    if other:
        prim.ApplyAPI(UNITS)
        for k, v in other.items():
            prim.GetAttribute(BASE[k][1]).Set(v)


def compensate_spatial(prim):
    """Author named compensation ops so `prim` matches its parent's spatial metrics."""
    own_mpu, _ = compute_effective(prim, "L")
    own_up, _ = compute_effective(prim, "upAxis")
    tgt_mpu, _ = compute_effective(prim.GetParent(), "L")
    tgt_up, _ = compute_effective(prim.GetParent(), "upAxis")
    prim.ApplyAPI(COMP)
    prim.GetAttribute("metricsCompensation:desired").Set(True)
    x = UsdGeom.Xformable(prim)
    order = [op.GetOpName() for op in x.GetOrderedXformOps()]
    if own_up != tgt_up:
        name = "xformOp:rotateX:metricsCompensation"
        angle = -90.0 if (own_up, tgt_up) == ("Z", "Y") else 90.0
        if name in order:
            prim.GetAttribute(name).Set(angle)
        else:
            x.AddRotateXOp(opSuffix="metricsCompensation").Set(angle)
    if own_mpu != tgt_mpu:
        s = own_mpu / tgt_mpu
        name = "xformOp:scale:metricsCompensation"
        if name in order:
            prim.GetAttribute(name).Set((s, s, s))
        else:
            x.AddScaleOp(opSuffix="metricsCompensation").Set((s, s, s))


def author_from_source(attr, value, unit, to_si, offset_to_si=0.0):
    """Store `value` given in `unit` (SI = value * to_si + offset_to_si) in the prim's
    unit system, and record the source on the attribute.

    Offsets cover Celsius and Fahrenheit source data without putting offsets into the
    unit system: the stored temperature is always on an absolute (kelvin-like) scale.
    """
    dim = get_dimension(attr)
    if dim is None:
        raise ValueError(f"{attr.GetPath()} has no declared dimension")
    si = value * to_si + offset_to_si
    attr.Set(si / factor(dim, unit_system(attr.GetPrim())))
    attr.SetCustomDataByKey("unitSource", {
        "value": float(value),
        "unit": unit,
        "toSI": float(to_si),
        "offsetToSI": float(offset_to_si),
    })
