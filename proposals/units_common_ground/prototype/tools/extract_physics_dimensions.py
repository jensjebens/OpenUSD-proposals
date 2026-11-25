"""Turn the "Units:" clauses in UsdPhysics' schema.usda into a dimension table.

UsdPhysics' schema source states a unit expression for 25 attributes, but usdGenSchema
clears property customData (and the doc strings that carry these clauses never reach the
runtime as structured data). This script recovers them so the prototype can treat
UsdPhysics as if it declared `unitDimension` on each attribute.

Usage: python extract_physics_dimensions.py <path to usdPhysics/schema.usda> <out.json>
"""
import json
import re
import sys

from pxr import Sdf

TOKENS = {"mass": "M", "distance": "L", "dist_units": "L", "second": "T", "degrees": "angle"}


def parse(expr):
    """'mass*distance/second/second' -> {'M': 1, 'L': 1, 'T': -2}. Angles kept as 'angle'."""
    dims, sign = {}, 1
    for tok in re.findall(r"[A-Za-z_]+|[*/]", expr):
        if tok == "*":
            sign = 1
        elif tok == "/":
            sign = -1
        else:
            base = TOKENS[tok.lower()]
            dims[base] = dims.get(base, 0) + sign
    return {k: v for k, v in dims.items() if v}


def main(src, out):
    layer = Sdf.Layer.FindOrOpen(src)
    table = {}
    for prim in layer.rootPrims:
        for prop in prim.properties:
            doc = " ".join((prop.documentation or "").split())
            m = re.search(r"Units:\s*(.*)", doc)
            if not m:
                continue
            text = m.group(1)
            key = f"{prim.name}.{prop.name}"
            cond = re.search(r"if linear drive:\s*(.+?)\s+if angular drive:\s*([^ .]+)", text, re.I)
            either = re.match(r"degrees or distance depending on trans or rot", text)
            if cond:
                table[key] = {"linear": parse(cond.group(1)), "angular": parse(cond.group(2)),
                              "source": text}
            elif either:
                table[key] = {"linear": {"L": 1}, "angular": {"angle": 1}, "source": text}
            else:
                expr = re.match(r"[A-Za-z_*/ ]+", text).group(0)
                table[key] = {"dimension": parse(expr), "source": text}
    with open(out, "w") as f:
        json.dump(table, f, indent=2, sort_keys=True)
    print(f"{len(table)} attributes, "
          f"{sum('linear' in v for v in table.values())} depend on the applied instance")


if __name__ == "__main__":
    main(*sys.argv[1:3])
