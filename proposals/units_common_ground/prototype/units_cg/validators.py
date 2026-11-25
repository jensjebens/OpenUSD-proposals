"""Validators. Codes starting PR114- are stand-ins for PR 114's own validators; codes
starting CG- are the common-ground additions.

Each returns a list of Finding. `validate(stage)` runs them all.
"""
from dataclasses import dataclass

from pxr import Pcp, Sdf, Usd

from .dimensions import factor, get_dimension
from .resolve import (BASE, SPATIAL, UNITS, UP_AXIS, _fallback, compute_effective,
                      parent_context, unit_system)

COMP = "SpatialMetricsXformCompensationAPI"
REL_TOL = 1e-9


@dataclass
class Finding:
    code: str
    severity: str  # error | warning
    path: str
    message: str

    def __str__(self):
        return f"{self.severity.upper():7} {self.code:14} {self.path}: {self.message}"


def _close(a, b):
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-300)


def _prims(stage):
    return Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate))


# --- PR 114 stand-ins -----------------------------------------------------------------

def pr114_root_prims(stage):
    out = []
    for p in stage.GetPseudoRoot().GetChildren():
        if p.GetSpecifier() == Sdf.SpecifierDef and not p.HasAPI(SPATIAL):
            out.append(Finding("PR114-1", "error", str(p.GetPath()),
                               "root prim has no SpatialMetricsAPI"))
    return out


def pr114_reference_has_schema(stage):
    out = []
    for p in _prims(stage):
        if (p.HasAuthoredReferences() or p.HasAuthoredPayloads()) and not p.HasAPI(SPATIAL):
            out.append(Finding("PR114-2", "warning", str(p.GetPath()),
                               "referenced prim does not carry SpatialMetricsAPI itself; "
                               "its source units may be lost across the arc"))
    return out


def _expected_scale(p):
    own, _ = compute_effective(p, "L")
    tgt, _ = compute_effective(p.GetParent(), "L")
    return own / tgt


def pr114_compensation(stage):
    """PR 114 validators 3 and 4: a spatial mismatch with the parent must be compensated,
    and the compensation must reconcile it, unless metricsCompensation:desired is false."""
    out = []
    for p in _prims(stage):
        if not p.HasAPI(SPATIAL) or p.GetParent().IsPseudoRoot():
            continue
        ctx = parent_context(p)
        own_l, _ = compute_effective(p, "L")
        own_up, _ = compute_effective(p, "upAxis")
        if _close(own_l, ctx["L"]) and own_up == ctx["upAxis"]:
            continue
        if p.HasAPI(COMP) and not p.GetAttribute("metricsCompensation:desired").Get():
            continue
        ops = p.GetAttribute("xformOpOrder").Get() or []
        if "xformOp:scale:metricsCompensation" not in ops and not _close(own_l, ctx["L"]):
            out.append(Finding("PR114-3", "error", str(p.GetPath()),
                               f"metersPerUnit {own_l:g} under a {ctx['L']:g} parent, "
                               "no compensation"))
        elif "xformOp:scale:metricsCompensation" in ops:
            s = p.GetAttribute("xformOp:scale:metricsCompensation").Get()[0]
            # PR 114 declares the op float3, so allow float rounding.
            if abs(s - _expected_scale(p)) > 1e-6 * abs(_expected_scale(p)):
                out.append(Finding("PR114-4", "error", str(p.GetPath()),
                                   f"compensation scale {s:g} does not reconcile "
                                   f"{own_l:g} -> {ctx['L']:g} (needs {_expected_scale(p):g})"))
        if own_up != ctx["upAxis"] and "xformOp:rotateX:metricsCompensation" not in ops:
            out.append(Finding("PR114-3", "error", str(p.GetPath()),
                               f"upAxis {own_up} under a {ctx['upAxis']} parent, "
                               "no compensation"))
    return out


# --- Common-ground additions ----------------------------------------------------------

def cg_relocates(stage):
    """CG-1: a relocated prim keeps the units it had at its source.

    Same reasoning as PR 114 validator 2 for references, applied to relocates: if the
    source parent and the target parent resolve differently, the relocated prim must
    carry the schemas itself."""
    out = []
    for layer in stage.GetLayerStack(includeSessionLayers=False):
        for src, tgt in layer.relocates:
            prim = stage.GetPrimAtPath(tgt)
            src_parent = stage.GetPrimAtPath(src.GetParentPath())
            if not prim or not src_parent:
                continue
            before = unit_system(src_parent)
            before["upAxis"] = compute_effective(src_parent, "upAxis")[0]
            after = parent_context(prim)
            changed = [b for b in before
                       if (before[b] != after[b] if b == "upAxis"
                           else not _close(before[b], after[b]))]
            lost = [b for b in changed
                    if not prim.HasAPI(SPATIAL if b in ("L", "upAxis") else UNITS)]
            if lost:
                out.append(Finding(
                    "CG-1", "error", str(tgt),
                    f"relocated from {src}; units {', '.join(lost)} change from "
                    f"{', '.join(str(before[b]) for b in lost)} to "
                    f"{', '.join(str(after[b]) for b in lost)} and the prim does not "
                    "carry the schema itself"))
    return out


def cg_class_units(stage):
    """CG-2: metrics schemas on a class prim reach every prim that inherits or
    specializes it, in whatever asset that prim lives. Flag it so the reach is visible."""
    out = []
    classes = [p for p in _prims(stage)
               if p.GetSpecifier() == Sdf.SpecifierClass and
               (p.HasAPI(SPATIAL) or p.HasAPI(UNITS))]
    for c in classes:
        users = []
        for p in _prims(stage):
            if p == c:
                continue
            q = Usd.PrimCompositionQuery(p)
            for arc in q.GetCompositionArcs():
                if (arc.GetArcType() in (Pcp.ArcTypeInherit, Pcp.ArcTypeSpecialize)
                        and arc.GetTargetPrimPath() == c.GetPath()):
                    users.append(str(p.GetPath()))
        out.append(Finding("CG-2", "warning", str(c.GetPath()),
                           "class carries units; they apply to "
                           f"{len(users)} prim(s): {', '.join(users) or 'none yet'}"))
    return out


def cg_partial_authoring(stage):
    """CG-3: applying a units schema makes the prim authoritative for every attribute of
    that schema. An unauthored attribute takes the schema fallback, not the ancestor's
    value. Warn when that silently changes a unit. Applies to PR 114's schema too."""
    out = []
    for p in _prims(stage):
        if p.GetParent().IsPseudoRoot():
            continue
        for base, (schema, attr) in list(BASE.items()) + [("upAxis", UP_AXIS)]:
            if not p.HasAPI(schema) or p.GetAttribute(attr).HasAuthoredValue():
                continue
            inherited, src = compute_effective(p.GetParent(), base)
            fb = _fallback(schema, attr)
            if src is not None and inherited != fb:
                out.append(Finding("CG-3", "warning", str(p.GetPath()),
                                   f"{attr} not authored: resets to fallback {fb} "
                                   f"instead of {inherited} from {src}"))
    return out


def cg_reference_unit_system(stage):
    """CG-4: PR 114 validator 2, extended to UnitSystemAPI. Only fires when the
    referenced subtree actually holds quantities with non-length dimensions."""
    out = []
    for p in _prims(stage):
        if not (p.HasAuthoredReferences() or p.HasAuthoredPayloads()) or p.HasAPI(UNITS):
            continue
        for d in Usd.PrimRange(p):
            hit = next((a for a in d.GetAttributes()
                        if a.HasAuthoredValue() and
                        any(k not in ("L", "angle") for k in (get_dimension(a) or {}))), None)
            if hit:
                out.append(Finding("CG-4", "warning", str(p.GetPath()),
                                   "referenced subtree holds "
                                   f"{hit.GetName()} but the prim does not carry "
                                   "UnitSystemAPI itself"))
                break
    return out


def cg_unit_source(stage):
    """CG-5: an attribute that records its source unit must still agree with it."""
    out = []
    for p in _prims(stage):
        for a in p.GetAttributes():
            rec = a.GetCustomDataByKey("unitSource")
            if not rec:
                continue
            dim = get_dimension(a)
            expected = (rec["value"] * rec["toSI"] + rec.get("offsetToSI", 0.0)) / \
                factor(dim, unit_system(p))
            if not _close(a.Get(), expected):
                out.append(Finding("CG-5", "error", str(a.GetPath()),
                                   f"value {a.Get():g} no longer matches its source "
                                   f"{rec['value']:g} {rec['unit']} (expects {expected:g})"))
    return out


ALL = [pr114_root_prims, pr114_reference_has_schema, pr114_compensation,
       cg_relocates, cg_class_units, cg_partial_authoring, cg_reference_unit_system,
       cg_unit_source]


def validate(stage, validators=ALL):
    out = []
    for v in validators:
        out.extend(v(stage))
    return out
