"""Scenario builders. Each writes its layers into `d` and returns the opened stage.

The cases come from the problem statement's concrete cases: the bolt and factory (PR 114's
own example), values from other sources in their own units, relocation, inherited units,
a sensor temperature, and a BGA package on a PCB for precision.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import units_cg  # noqa: E402,F401  (registers the schema plugin before pxr loads it)
from units_cg import apply_units, author_from_source, compensate_spatial  # noqa: E402

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, Vt  # noqa: E402


def _new(d, name):
    return Usd.Stage.CreateNew(os.path.join(d, name))


def _fresh(d, tag):
    """A new directory per scenario run, so layer identifiers never collide."""
    return tempfile.mkdtemp(prefix=tag + "_", dir=d)


def bolt_into_factory(d, compensate=True):
    """S1. A Z-up millimetre bolt referenced into a Y-up metre factory."""
    d = _fresh(d, "bolt_into_factory")
    b = _new(d, "bolt.usda")
    bolt = UsdGeom.Xform.Define(b, "/Bolt").GetPrim()
    apply_units(bolt, L=0.001, upAxis="Z")
    mesh = UsdGeom.Mesh.Define(b, "/Bolt/Shank")
    mesh.CreatePointsAttr([(0, 0, 0), (5, 0, 0), (0, 0, 40)])  # 40 mm long
    b.SetDefaultPrim(bolt)
    b.Save()

    f = _new(d, "factory.usda")
    fac = UsdGeom.Xform.Define(f, "/Factory").GetPrim()
    apply_units(fac, L=1.0, upAxis="Y")
    ref = UsdGeom.Xform.Define(f, "/Factory/Bolt").GetPrim()
    ref.GetReferences().AddReference("./bolt.usda")
    if compensate:
        compensate_spatial(ref)
    f.Save()
    return f


def density_in_grams(d):
    """S2. A part authored in grams and centimetres; a solver reads SI."""
    d = _fresh(d, "density_in_grams")
    s = _new(d, "part.usda")
    part = UsdGeom.Xform.Define(s, "/Part").GetPrim()
    apply_units(part, L=0.01, M=0.001)
    body = UsdGeom.Cube.Define(s, "/Part/Body").GetPrim()
    m = UsdPhysics.MassAPI.Apply(body)
    m.CreateDensityAttr(7.85)        # g/cm^3
    m.CreateMassAttr(1200.0)         # g
    m.CreateDiagonalInertiaAttr(Gf.Vec3f(10, 10, 10))  # g cm^2
    scene = UsdPhysics.Scene.Define(s, "/Part/Scene")
    scene.CreateGravityMagnitudeAttr(981.0)  # cm/s^2
    s.Save()
    return s


def temperature_one_schema(d):
    """S3. Temperature lives in the one unit-system schema; a thermal domain schema
    declares dimensions only. A Celsius sensor value is stored on the kelvin scale with
    its source recorded."""
    d = _fresh(d, "temperature_one_schema")
    s = _new(d, "board.usda")
    board = UsdGeom.Xform.Define(s, "/Board").GetPrim()
    apply_units(board, L=0.001, M=1.0, Theta=1.0)
    chip = UsdGeom.Cube.Define(s, "/Board/Chip").GetPrim()
    chip.ApplyAPI("ThermalBodyAPI")
    author_from_source(chip.GetAttribute("thermal:initialTemperature"), 85.0, "degC",
                       1.0, 273.15)
    chip.GetAttribute("thermal:conductivity").Set(0.15)  # W/(mm K) in a mm system
    chip.CreateAttribute("vendor:rating", Sdf.ValueTypeNames.Double).Set(3.0)
    s.Save()
    return s


def partial_authoring(d):
    """S4. A gripper applies UnitSystemAPI to say grams but does not restate time."""
    d = _fresh(d, "partial_authoring")
    s = _new(d, "robot.usda")
    r = UsdGeom.Xform.Define(s, "/Robot").GetPrim()
    apply_units(r, L=1.0, T=0.001)  # milliseconds
    g = UsdGeom.Xform.Define(s, "/Robot/Gripper").GetPrim()
    apply_units(g, M=0.001)
    s.Save()
    return s


def partial_spatial(d):
    """S4b. PR 114's own schema, partly authored. A robot is in metres, Z up. A tool applies
    SpatialMetricsAPI to the gripper only to author Z up (PR 114's ApplyAndAuthorUpAxis).
    The gripper's metersPerUnit is then the schema fallback, 0.01, not the robot's 1."""
    d = _fresh(d, "partial_spatial")
    s = _new(d, "robot.usda")
    r = UsdGeom.Xform.Define(s, "/Robot").GetPrim()
    apply_units(r, L=1.0, upAxis="Z")
    g = UsdGeom.Xform.Define(s, "/Robot/Gripper").GetPrim()
    apply_units(g, upAxis="Z")
    UsdGeom.Cube.Define(s, "/Robot/Gripper/Finger").CreateSizeAttr(0.02)  # 2 cm, in metres
    s.Save()
    return s


def relocated_gripper(d, fix=False):
    """S5. Relocation: a gripper under a millimetre tools prim is
    relocated under a metre work cell."""
    d = _fresh(d, "relocated_gripper")
    a = _new(d, "arm.usda")
    arm = UsdGeom.Xform.Define(a, "/Arm").GetPrim()
    apply_units(arm, L=1.0)
    tools = UsdGeom.Xform.Define(a, "/Arm/Tools").GetPrim()
    apply_units(tools, L=0.001)
    compensate_spatial(tools)
    UsdGeom.Xform.Define(a, "/Arm/Tools/Gripper")
    UsdGeom.Cube.Define(a, "/Arm/Tools/Gripper/Finger").CreateSizeAttr(20.0)  # 20 mm
    a.SetDefaultPrim(arm)
    a.Save()

    s = _new(d, "cell.usda")
    w = UsdGeom.Xform.Define(s, "/World").GetPrim()
    apply_units(w, L=1.0)
    UsdGeom.Xform.Define(s, "/World/Arm").GetPrim().GetReferences().AddReference("./arm.usda")
    UsdGeom.Xform.Define(s, "/World/Cell")
    layer = s.GetRootLayer()
    layer.relocates = [(Sdf.Path("/World/Arm/Tools/Gripper"), Sdf.Path("/World/Cell/Gripper"))]
    s.Save()
    s = Usd.Stage.Open(layer.identifier)
    if fix:
        # What a fixer would do, mirroring PR 114 validator 2's fixer: carry the source
        # units onto the relocated prim, then compensate it into its new parent.
        g = s.GetPrimAtPath("/World/Cell/Gripper")
        apply_units(g, L=0.001)
        compensate_spatial(g)
        s.Save()
    return s


def class_carries_units(d):
    """S6. A class prim carries SpatialMetricsAPI; two prims inherit it."""
    d = _fresh(d, "class_carries_units")
    s = _new(d, "classes.usda")
    root = UsdGeom.Xform.Define(s, "/Root").GetPrim()
    apply_units(root, L=1.0)
    c = s.CreateClassPrim("/_MillimetreParts")
    apply_units(c, L=0.001)
    for n in ("A", "B"):
        p = UsdGeom.Xform.Define(s, f"/Root/{n}").GetPrim()
        p.GetInherits().AddInherit("/_MillimetreParts")
        compensate_spatial(p)
    s.Save()
    return s


def vendor_density(d, tamper=False):
    """S7. A vendor catalogue gives density in g/cm^3; the asset is SI. The importer
    converts once and records the source."""
    d = _fresh(d, "vendor_density")
    s = _new(d, "steel.usda")
    root = UsdGeom.Xform.Define(s, "/Beam").GetPrim()
    apply_units(root, L=1.0, M=1.0)
    m = UsdPhysics.MassAPI.Apply(UsdGeom.Cube.Define(s, "/Beam/Body").GetPrim())
    attr = m.CreateDensityAttr()
    author_from_source(attr, 7.85, "g/cm^3", 1000.0)
    if tamper:
        attr.Set(7900.0)  # someone edits the value; the record now disagrees
    s.Save()
    return s


def drive_instances(d):
    """S8. UsdPhysics drive stiffness has a different dimension per applied instance."""
    d = _fresh(d, "drive_instances")
    s = _new(d, "drives.usda")
    root = UsdGeom.Xform.Define(s, "/Rig").GetPrim()
    apply_units(root, L=0.01, M=0.001)
    j = UsdPhysics.PrismaticJoint.Define(s, "/Rig/Slide").GetPrim()
    UsdPhysics.DriveAPI.Apply(j, "linear").CreateStiffnessAttr(100.0)
    r = UsdPhysics.RevoluteJoint.Define(s, "/Rig/Hinge").GetPrim()
    UsdPhysics.DriveAPI.Apply(r, "angular").CreateStiffnessAttr(100.0)
    s.Save()
    return s


def bga_on_pcb(d, scale_precision="float"):
    """S9. Precision across scales: a BGA package modelled in micrometres placed on a PCB
    modelled in metres, 0.2 m from the board origin. Returns (stage, worst error in m)
    between the composed solder-ball positions and the exact positions."""
    d = _fresh(d, "bga_on_pcb")
    p = _new(d, f"bga_{scale_precision}.usda")
    pkg = UsdGeom.Xform.Define(p, "/Package").GetPrim()
    apply_units(pkg, L=1e-6)
    balls = [(x * 800.0 + 123.456, y * 800.0 + 654.321, 250.0)  # µm, 0.8 mm pitch
             for x in range(20) for y in range(20)]
    UsdGeom.Points.Define(p, "/Package/Balls").CreatePointsAttr(Vt.Vec3fArray(balls))
    p.SetDefaultPrim(pkg)
    p.Save()

    s = _new(d, f"pcb_{scale_precision}.usda")
    board = UsdGeom.Xform.Define(s, "/Board").GetPrim()
    apply_units(board, L=1.0)
    ref = UsdGeom.Xform.Define(s, "/Board/U1")
    ref.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.2, 0.15, 0.0016))
    ref.GetPrim().GetReferences().AddReference(f"./bga_{scale_precision}.usda")
    k = 1e-6 / 1.0
    if scale_precision == "float":
        # PR 114 declares xformOp:scale:metricsCompensation as float3.
        ref.GetPrim().ApplyAPI("SpatialMetricsXformCompensationAPI")
        ref.AddScaleOp(opSuffix="metricsCompensation").Set(Gf.Vec3f(k, k, k))
    else:
        # Experiment only: a double3 op of the same name, without the schema.
        ref.AddScaleOp(UsdGeom.XformOp.PrecisionDouble,
                       opSuffix="metricsCompensation").Set(Gf.Vec3d(k, k, k))
    s.Save()

    pts = UsdGeom.Points(s.GetPrimAtPath("/Board/U1/Balls"))
    xf = pts.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    worst_scale = worst_storage = 0.0
    for stored, intended in zip(pts.GetPointsAttr().Get(), balls):
        sd = Gf.Vec3d(stored)
        got = xf.Transform(sd)
        exact = Gf.Vec3d(0.2, 0.15, 0.0016) + sd * 1e-6
        worst_scale = max(worst_scale, (got - exact).GetLength())
        worst_storage = max(worst_storage, (sd - Gf.Vec3d(*intended)).GetLength() * 1e-6)
    return s, {"compensation": worst_scale, "float points": worst_storage}
