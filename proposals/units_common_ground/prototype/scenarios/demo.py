"""Run every scenario and print what the resolver, reader and validators report.

python scenarios/demo.py [outdir]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import scenarios as S  # noqa: E402
from units_cg import MissingDimension, compute_effective, read_in, validate  # noqa: E402
from units_cg.convert import describe  # noqa: E402

from pxr import Usd  # noqa: E402


def show(title, stage):
    print(f"\n=== {title}")
    findings = validate(stage)
    for f in findings:
        print("  ", f)
    if not findings:
        print("   validators: clean")
    return findings


def main(d):
    s = S.bolt_into_factory(d, compensate=False)
    show("S1a bolt (mm, Z-up) into factory (m, Y-up), no compensation", s)
    s = S.bolt_into_factory(d, compensate=True)
    show("S1b same, compensated with PR 114's named ops", s)
    flat = Usd.Stage.Open(s.Flatten())
    b = flat.GetPrimAtPath("/Factory/Bolt/Shank")
    print("   flattened: Shank metersPerUnit =", compute_effective(b, "L")[0],
          "upAxis =", compute_effective(b, "upAxis")[0])
    show("S1c flattened stage", flat)

    s = S.density_in_grams(d)
    show("S2 part in grams and centimetres, read by a solver in SI", s)
    for p in ("/Part/Body.physics:density", "/Part/Body.physics:mass",
              "/Part/Body.physics:diagonalInertia", "/Part/Scene.physics:gravityMagnitude"):
        a = s.GetAttributeAtPath(p)
        print(f"   {describe(a)}: authored {a.Get()} -> SI {read_in(a)}")

    s = S.temperature_one_schema(d)
    show("S3 temperature in the one unit-system schema", s)
    for p in ("/Board/Chip.thermal:initialTemperature", "/Board/Chip.thermal:conductivity"):
        a = s.GetAttributeAtPath(p)
        print(f"   {describe(a)}: authored {a.Get()} -> SI {read_in(a)}")
    print("   source record:", dict(s.GetAttributeAtPath(
        "/Board/Chip.thermal:initialTemperature").GetCustomDataByKey("unitSource")))
    try:
        read_in(s.GetAttributeAtPath("/Board/Chip.vendor:rating"))
    except MissingDimension as e:
        print("   consumer error:", e)

    show("S4 gripper says grams, forgets milliseconds", S.partial_authoring(d))

    show("S5a relocated gripper", S.relocated_gripper(d))
    s = S.relocated_gripper(d, fix=True)
    show("S5b relocated gripper after the fixer", s)
    f = s.GetPrimAtPath("/World/Cell/Gripper/Finger")
    print("   finger metersPerUnit =", compute_effective(f, "L")[0])

    show("S6 class prim carries units", S.class_carries_units(d))

    show("S7a vendor density converted at import", S.vendor_density(d))
    s = S.vendor_density(d, tamper=True)
    show("S7b same, value edited afterwards", s)

    s = S.drive_instances(d)
    show("S8 drive stiffness, linear vs angular instance", s)
    for p in ("/Rig/Slide.drive:linear:physics:stiffness",
              "/Rig/Hinge.drive:angular:physics:stiffness"):
        a = s.GetAttributeAtPath(p)
        print(f"   {describe(a)}: authored {a.Get()} -> SI {read_in(a)}")

    print("\n=== S9 BGA in micrometres on a PCB in metres, 0.2 m from the origin")
    for prec in ("float", "double"):
        _, err = S.bga_on_pcb(d, prec)
        print(f"   {prec:6} compensation scale: worst error {err['compensation']:.3e} m;"
              f" float points in µm: {err['float points']:.3e} m")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="units_cg_")
    os.makedirs(out, exist_ok=True)
    print("layers in", out)
    main(out)
