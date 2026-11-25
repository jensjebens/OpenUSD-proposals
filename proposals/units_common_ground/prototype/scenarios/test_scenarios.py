"""pytest scenarios/test_scenarios.py"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import scenarios as S  # noqa: E402
from units_cg import MissingDimension, compute_effective, read_in, validate  # noqa: E402

from pxr import Usd  # noqa: E402


def codes(stage):
    return sorted(f.code for f in validate(stage))


def test_s1_bolt_uncompensated_is_flagged(tmp_path):
    assert codes(S.bolt_into_factory(str(tmp_path), compensate=False)) == ["PR114-3", "PR114-3"]


def test_s1_bolt_compensated_survives_flatten(tmp_path):
    s = S.bolt_into_factory(str(tmp_path))
    assert codes(s) == []
    flat = Usd.Stage.Open(s.Flatten())
    assert codes(flat) == []
    shank = flat.GetPrimAtPath("/Factory/Bolt/Shank")
    assert compute_effective(shank, "L")[0] == 0.001
    assert compute_effective(shank, "upAxis")[0] == "Z"


def test_s2_solver_reads_si(tmp_path):
    s = S.density_in_grams(str(tmp_path))
    assert codes(s) == []
    assert read_in(s.GetAttributeAtPath("/Part/Body.physics:density")) == pytest.approx(7850, rel=1e-6)
    assert read_in(s.GetAttributeAtPath("/Part/Body.physics:mass")) == pytest.approx(1.2)
    assert read_in(s.GetAttributeAtPath("/Part/Scene.physics:gravityMagnitude")) == pytest.approx(9.81)
    assert read_in(s.GetAttributeAtPath("/Part/Body.physics:diagonalInertia"))[0] == pytest.approx(1e-6)


def test_s3_temperature_and_missing_dimension(tmp_path):
    s = S.temperature_one_schema(str(tmp_path))
    assert codes(s) == []
    assert s.GetAttributeAtPath("/Board/Chip.thermal:initialTemperature").Get() == pytest.approx(358.15)
    assert read_in(s.GetAttributeAtPath("/Board/Chip.thermal:conductivity")) == pytest.approx(1.5e-4)
    with pytest.raises(MissingDimension):
        read_in(s.GetAttributeAtPath("/Board/Chip.vendor:rating"))


def test_s4_partial_authoring_warns(tmp_path):
    assert codes(S.partial_authoring(str(tmp_path))) == ["CG-3"]


def test_s4b_partial_spatial_falls_back_to_centimetres(tmp_path):
    s = S.partial_spatial(str(tmp_path))
    finger = s.GetPrimAtPath("/Robot/Gripper/Finger")
    assert compute_effective(finger, "L")[0] == pytest.approx(0.01)
    assert compute_effective(finger, "upAxis")[0] == "Z"
    # PR 114's own validator sees a metersPerUnit mismatch; CG-3 names the cause.
    assert codes(s) == ["CG-3", "PR114-3"]


def test_s5_relocate(tmp_path):
    assert codes(S.relocated_gripper(str(tmp_path))) == ["CG-1"]
    fixed = S.relocated_gripper(str(tmp_path), fix=True)
    assert codes(fixed) == []
    assert compute_effective(fixed.GetPrimAtPath("/World/Cell/Gripper/Finger"), "L")[0] == 0.001


def test_s6_class_units_flagged(tmp_path):
    assert codes(S.class_carries_units(str(tmp_path))) == ["CG-2"]


def test_s7_unit_source_record(tmp_path):
    assert codes(S.vendor_density(str(tmp_path))) == []
    assert codes(S.vendor_density(str(tmp_path), tamper=True)) == ["CG-5"]


def test_s8_drive_dimension_depends_on_instance(tmp_path):
    s = S.drive_instances(str(tmp_path))
    assert read_in(s.GetAttributeAtPath("/Rig/Slide.drive:linear:physics:stiffness")) == pytest.approx(0.1)
    assert read_in(s.GetAttributeAtPath("/Rig/Hinge.drive:angular:physics:stiffness")) == pytest.approx(1e-5)


def test_s9_float_compensation_below_float_point_error(tmp_path):
    _, err = S.bga_on_pcb(str(tmp_path), "float")
    assert err["compensation"] < err["float points"]
