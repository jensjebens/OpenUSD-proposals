"""Consumer-side reads. Nothing here writes to the stage.

A solver asks for a value in the units it computes in; the authored value stays the
only source of truth. A physics engine chooses its own consistent working units and
asks for every value in them.
"""
from pxr import Gf, Usd

from .dimensions import factor, format_dimension, get_dimension
from .resolve import unit_system

SI = {b: 1.0 for b in ("L", "M", "T", "I", "Theta", "N", "J")}


class MissingDimension(Exception):
    pass


def _scale(value, k):
    if isinstance(value, (int, float)):
        return value * k
    if isinstance(value, (Gf.Vec3f, Gf.Vec3d)):
        return type(value)(*(c * k for c in value))
    try:  # VtArray of scalars
        return type(value)([v * k for v in value])
    except TypeError:
        raise TypeError(f"cannot scale {type(value).__name__}")


def read_in(attr, target=SI, time=Usd.TimeCode.Default()):
    """Value of `attr` converted into the `target` unit system (default SI)."""
    dim = get_dimension(attr)
    if dim is None:
        raise MissingDimension(f"{attr.GetPath()} has no declared dimension")
    src = unit_system(attr.GetPrim())
    k = factor(dim, src) / factor(dim, target)
    return _scale(attr.Get(time), k)


def describe(attr):
    dim = get_dimension(attr)
    return f"{attr.GetPath()} [{format_dimension(dim) if dim is not None else 'unknown'}]"
