"""R0.6.7: optional, explicit uniform-longitudinal-fire coupling.

This module automates data TRANSFER, never infer the temperature distribution
along a member without user confirmation. All physical inputs and methods are
provenanced and every output remains diagnostic (not R90 evidence).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from .r064d import (MemberEvidenceInputError, sample_station_bundle,
                    evaluate_explicit_member_bundle)
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.normative.actions import ACTION_INPUT_CONTRACT, action_source

VERSION = "R0.6.7-uniform-longitudinal-thermal-member-diagnostic-v1"
SUPPORTS = ("pinned", "fixed", "guided")
MODES = ("not_defined", "axial_only", "uniform_transverse_load")
THERMAL_MODES = ("explicit_only", "uniform_assumed")


def _number(value, title):
    if isinstance(value, bool):
        raise MemberEvidenceInputError(f"{title}: finite number required")
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise MemberEvidenceInputError(f"{title}: finite number required") from exc
    if not math.isfinite(x):
        raise MemberEvidenceInputError(f"{title}: finite number required")
    return x


def validate_member_spec(spec):
    """Validate explicit choices; never fill missing supports or actions."""
    if spec is None:
        return {}
    if not isinstance(spec, dict):
        raise MemberEvidenceInputError("member_spec must be an object")
    # SP-R.3 is a distinct, stricter source contract. Validate its JSON
    # structure here BEFORE canonical project validation; the SP-R.3 member
    # solver additionally validates actual column geometry, stations and N.
    # Do not discard unknown fields or coerce this contract to legacy R0.6.7.
    if spec.get("load_mode") == "explicit_sp2026_beam":
        expected = {"load_mode", "z_m", "N_kN", "left_support",
            "right_support", "axial_restraint_mode", "fire_design_action_source",
            "distributed_load_kNpm", "nodal_forces", "transverse_action_source",
            "initial_imperfection", "imperfection_source",
            "entered_section_moments_reconciled", "longitudinal_thermal_mode",
            "uniform_exposure_confirmed", "history_times_minutes",
            "thermal_longitudinal_mode","resistance_scan_requested",
            "resistance_scan_max_factor","resistance_scan_step",
            "resistance_scan_first_factor","resistance_time_history_requested",
            "constitutive_model","global_stability_requested",
            "nominal_sp5_requested","nominal_sp5_phi_eff",
            "nominal_sp5_creep_provenance","nominal_sp5_history_requested"}
        unknown = set(spec) - expected
        if unknown:
            raise MemberEvidenceInputError("SP-R3 member_spec unknown fields: "+
                ", ".join(sorted(unknown)))
        required = expected - {"history_times_minutes", "thermal_longitudinal_mode",
            "resistance_scan_requested","resistance_scan_max_factor",
            "resistance_scan_step","resistance_scan_first_factor",
            "resistance_time_history_requested","constitutive_model",
            "global_stability_requested","nominal_sp5_requested",
            "nominal_sp5_phi_eff","nominal_sp5_creep_provenance",
            "nominal_sp5_history_requested"}
        missing = sorted(required-set(spec))
        if missing:
            raise MemberEvidenceInputError("SP-R3 member_spec missing fields: "+
                ", ".join(missing))
        n = len(spec["z_m"]) if isinstance(spec["z_m"],(tuple,list)) else 0
        if not 3 <= n <= 25:
            raise MemberEvidenceInputError("SP-R3 requires 3..25 explicit beam stations")
        z = [_number(v, "z_m") for v in spec["z_m"]]
        if abs(z[0]) > 1.e-10 or any(b <= a for a,b in zip(z,z[1:])):
            raise MemberEvidenceInputError("SP-R3 member stations must start at 0 and increase")
        if _number(spec["N_kN"], "N_kN") <= 0.:
            raise MemberEvidenceInputError("SP-R3 positive axial compression required")
        if spec["axial_restraint_mode"] != "free_axial_expansion":
            raise MemberEvidenceInputError("SP-R3 axial thermal restraint not yet supported")
        for side in ("left_support", "right_support"):
            s = spec[side]
            if (not isinstance(s,dict) or set(s)!={"x","y"} or
                any(s[a] not in ("pinned","fixed","guided","free") for a in ("x","y"))):
                raise MemberEvidenceInputError("SP-R3 "+side+" requires explicit x/y conditions")
        for key,size in (("distributed_load_kNpm",n),
                         ("nodal_forces",4*n),("initial_imperfection",4*n)):
            row = spec[key]
            if not isinstance(row,(tuple,list)) or len(row)!=size:
                raise MemberEvidenceInputError("SP-R3 "+key+" length mismatch")
            if key=="distributed_load_kNpm":
                if any(not isinstance(x,(tuple,list)) or len(x)!=2 for x in row):
                    raise MemberEvidenceInputError("SP-R3 each distributed load must have x/y")
                for pair in row:
                    for v in pair:_number(v,key)
            else:
                for v in row:_number(v,key)
        for key in ("fire_design_action_source","transverse_action_source",
                    "imperfection_source"):
            if not isinstance(spec[key],str) or not spec[key].strip():
                raise MemberEvidenceInputError("SP-R3 "+key+" provenance required")
        if type(spec["entered_section_moments_reconciled"]) is not bool:
            raise MemberEvidenceInputError("SP-R3 explicit moment reconciliation flag required")
        mode = spec["longitudinal_thermal_mode"]
        if mode not in ("explicit_uniform_full_length","explicit_per_station"):
            raise MemberEvidenceInputError("SP-R3 longitudinal temperature mode invalid")
        if type(spec["uniform_exposure_confirmed"]) is not bool:
            raise MemberEvidenceInputError("SP-R3 uniform heating flag must be Boolean")
        if mode=="explicit_uniform_full_length" and not spec["uniform_exposure_confirmed"]:
            raise MemberEvidenceInputError("SP-R3 uniform full-length fire not confirmed")
        if "history_times_minutes" in spec:
            times=spec["history_times_minutes"]
            if not isinstance(times,(tuple,list)) or not 1<=len(times)<=24:
                raise MemberEvidenceInputError("SP-R3 history requires 1..24 times")
            vals=[_number(v,"history time") for v in times]
            if vals[0]<=0 or any(b<=a for a,b in zip(vals,vals[1:])):
                raise MemberEvidenceInputError("SP-R3 history times must be positive/increasing")
        if "constitutive_model" in spec and spec["constitutive_model"] not in (
                "SP5_6_1_5_4_SECTION_CHECK",
                "SP5_6_1_5_2_FULL_HOT_EXPLORATORY"):
            raise MemberEvidenceInputError("SP-R5 unknown full/simplified SP5 constitutive mode")
        if "global_stability_requested" in spec and type(spec["global_stability_requested"]) is not bool:
            raise MemberEvidenceInputError("SP-R5 global stability must be explicit Boolean")
        if "resistance_time_history_requested" in spec:
            if type(spec["resistance_time_history_requested"]) is not bool:
                raise MemberEvidenceInputError("SP-R4 resistance history request must be Boolean")
            if spec["resistance_time_history_requested"] and spec.get("resistance_scan_requested") is not True:
                raise MemberEvidenceInputError("SP-R4 time-dependent capacity requires capacity scan activation")
        if "nominal_sp5_requested" in spec and type(spec["nominal_sp5_requested"]) is not bool:
            raise MemberEvidenceInputError("SP-R6 nominal route requires Boolean opt-in")
        if "nominal_sp5_history_requested" in spec:
            if type(spec["nominal_sp5_history_requested"]) is not bool:
                raise MemberEvidenceInputError("SP-R6 history requested must be Boolean")
            if spec["nominal_sp5_history_requested"] and spec.get("nominal_sp5_requested") is not True:
                raise MemberEvidenceInputError("SP-R6 nominal history requires nominal route")
        if spec.get("nominal_sp5_requested") is True:
            phi=_number(spec.get("nominal_sp5_phi_eff"),"SP-R6 effective creep")
            if not 0<=phi<=100.:
                raise MemberEvidenceInputError("SP-R6 effective creep outside 0..100")
            source=spec.get("nominal_sp5_creep_provenance")
            if not isinstance(source,str) or not source.strip():
                raise MemberEvidenceInputError("SP-R6 effective creep provenance required")
        elif any(k in spec for k in ("nominal_sp5_phi_eff",
                                    "nominal_sp5_creep_provenance")):
            raise MemberEvidenceInputError("SP-R6 creep controls require nominal route")
        if "resistance_scan_requested" in spec and type(spec["resistance_scan_requested"]) is not bool:
            raise MemberEvidenceInputError("SP-R4 resistance scan activation must be Boolean")
        if any(k in spec for k in (
                "resistance_scan_max_factor","resistance_scan_step",
                "resistance_scan_first_factor")):
            if spec.get("resistance_scan_requested") is not True:
                raise MemberEvidenceInputError("SP-R4 scan controls require explicit activation")
            start=_number(spec.get("resistance_scan_first_factor",.25),"SP-R4 first factor")
            step=_number(spec.get("resistance_scan_step",.25),"SP-R4 step")
            stop=_number(spec.get("resistance_scan_max_factor",2.),"SP-R4 maximum")
            if not 0<start<=stop<=5. or not 0<step<=stop:
                raise MemberEvidenceInputError("SP-R4 factor-scan controls out of range")
        return copy.deepcopy(spec)

    keys = {"thermal_longitudinal_mode", "uniform_fire_basis", "left_support",
            "right_support", "load_mode", "q_x_kNpm", "q_y_kNpm",
            "fire_actions_source", "support_provenance", "node_count"}
    unknown = set(spec) - keys
    if unknown:
        raise MemberEvidenceInputError("member_spec unknown fields: " + ", ".join(sorted(unknown)))
    if spec.get("thermal_longitudinal_mode", "explicit_only") not in THERMAL_MODES:
        raise MemberEvidenceInputError("invalid thermal_longitudinal_mode")
    if spec.get("load_mode", "not_defined") not in MODES:
        raise MemberEvidenceInputError("invalid member load_mode")
    for key in ("left_support", "right_support"):
        if spec.get(key) is not None and spec[key] not in SUPPORTS:
            raise MemberEvidenceInputError(f"{key}: choose pinned, fixed or guided")
    if "node_count" in spec and (type(spec["node_count"]) is not int or not 2 <= spec["node_count"] <= 21):
        raise MemberEvidenceInputError("node_count must be an integer in 2..21")
    for key in ("q_x_kNpm", "q_y_kNpm"):
        if spec.get(key) is not None:
            _number(spec[key], key)
    for key in ("uniform_fire_basis", "fire_actions_source", "support_provenance"):
        if spec.get(key) is not None and (not isinstance(spec[key], str) or not spec[key].strip()):
            raise MemberEvidenceInputError(f"{key}: nonempty explanation required")
    return copy.deepcopy(spec)


def _source(column, thermal):
    """Proof that the source thermal object matches current authoring state."""
    spec = column.get("thermal_spec") or {}
    if thermal.get("status") not in ("evaluated", "evaluated_with_scope_warnings"):
        raise MemberEvidenceInputError("Annex K temperature field is not evaluated")
    faces = spec.get("exposed_faces")
    if not isinstance(faces, (list, tuple)) or set(faces) != set(thermal.get("exposed_faces") or ()):
        raise MemberEvidenceInputError("heated faces differ between source and thermal field")
    if abs(_number(thermal.get("fire_minutes"), "thermal.fire_minutes")
           - _number(column.get("fire_minutes"), "column.fire_minutes")) > 1e-8:
        raise MemberEvidenceInputError("fire time differs between source and computed thermal field")
    if not isinstance(thermal.get("coefficients"), dict):
        raise MemberEvidenceInputError("thermal coefficients and provenance required")
    if any("вне интервала 20--1220" in str(x) or str(x).startswith("К.6:") for x in thermal.get("issues", [])):
        raise MemberEvidenceInputError("Annex K temperature field outside valid approximation")
    return {
        "thermal_source": str(thermal.get("source")),
        "thermal_release": str(thermal.get("release")),
        "time_minutes": float(thermal["fire_minutes"]),
        "heated_faces": sorted(faces),
        "a_red_m2_h": float(thermal["coefficients"]["a_red_m2_h"]),
        "K2_density_status": thermal["coefficients"].get("K2_density_status"),
        "thermal_scope_warnings": list(thermal.get("issues") or []),
    }


def build_uniform_fire_bundle(column, *, thermal=None, member_spec=None):
    """Generate nodal and 3-point Gauss fields for uniform heating along z.

    Identical temperature fields are generated for EACH required station only
    when the user explicitly accepts a longitudinally uniform exposure.
    Temperatures are not inferred from an arbitrary station, interpolated in z
    or taken from an unrelated column. Member actions remain independent from
    tabular section moments. The resulting bundle stays diagnostic.
    """
    spec = validate_member_spec(member_spec if member_spec is not None else column.get("member_spec"))
    if spec.get("thermal_longitudinal_mode") != "uniform_assumed":
        raise MemberEvidenceInputError("UNIFORM_HEATING_ASSUMPTION_REQUIRED: choose explicit uniform heating along member")
    note = spec.get("uniform_fire_basis")
    if not isinstance(note, str) or not note.strip():
        raise MemberEvidenceInputError("uniform_fire_basis: justify equal heating for all longitudinal stations")
    if any(spec.get(k) not in SUPPORTS for k in ("left_support", "right_support")):
        raise MemberEvidenceInputError("both physical end support types must be selected explicitly")
    if spec.get("load_mode", "not_defined") == "not_defined":
        raise MemberEvidenceInputError("MEMBER_LOAD_MODEL_REQUIRED: do not infer a load diagram from section moments")
    source_thermal = thermal if thermal is not None else evaluate_rectangular_column(column, grid=12)
    source = _source(column, source_thermal)
    count = spec.get("node_count", 3)
    bundle = sample_station_bundle(column, node_count=count)
    if bundle["N_kN"] is None:
        raise MemberEvidenceInputError("CONSTANT_N_REQUIRED: all sections must have complete and consistent compression")
    if spec["load_mode"] == "axial_only":
        for s in bundle["section_actions_reference_only"]:
            if abs(float(s["Mx_kNm"])) > 1e-9 or abs(float(s["My_kNm"])) > 1e-9:
                raise MemberEvidenceInputError("AXIAL_ONLY_CONFLICTS_WITH_SECTION_MOMENTS")
        qx = qy = 0.0
    else:
        if spec.get("q_x_kNpm") is None or spec.get("q_y_kNpm") is None:
            raise MemberEvidenceInputError("explicit uniform transverse q_x and q_y required")
        qx = _number(spec["q_x_kNpm"], "q_x_kNpm")
        qy = _number(spec["q_y_kNpm"], "q_y_kNpm")
    for row in bundle["gauss_stations"]:
        for e in row:
            e["thermal"] = copy.deepcopy(source_thermal)
    for e in bundle["node_stations"]:
        e["thermal"] = copy.deepcopy(source_thermal)
    bundle["left_support"] = {"kind": spec["left_support"]}
    bundle["right_support"] = {"kind": spec["right_support"]}
    bundle["distributed_load_kNpm"] = [[qx, qy] for _ in bundle["z_m"]]
    bundle["fire_actions_source"] = action_source(spec.get("fire_actions_source"))
    bundle["grid"] = 12
    bundle["r067_assumptions"] = {
        "version": VERSION,
        "longitudinal_temperature_model": "uniform_cross_section_user_assumed",
        "longitudinal_uniformity_accepted": True,
        "longitudinal_uniformity_basis": note.strip(),
        "support_provenance": spec.get("support_provenance") or None,
        "member_load_mode": spec["load_mode"],
        "fire_action_input_contract": ACTION_INPUT_CONTRACT,
        "fire_design_actions_accepted_as_entered": True,
        "section_moments_not_converted_to_transverse_loads": True,
        "source_thermal": source,
        "temperature_source_sha256": hashlib.sha256(json.dumps(
            {"thermal": source_thermal, "column_id": column.get("id")},
            ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(),
        "normative_claim": False,
    }
    bundle["method_notice"] = ("R0.6.7: identical Annex K temperature data repeated at each "
        "longitudinal station ONLY by explicit user assumption; R90 not qualified. "
        "Section Mx/My are not converted to distributed loads.")
    return bundle


def evaluate_uniform_fire_member(column, *, thermal=None, member_spec=None):
    """Run optional diagnostic or report fail-closed, preserving source reasons."""
    try:
        bundle = build_uniform_fire_bundle(column, thermal=thermal, member_spec=member_spec)
        result = evaluate_explicit_member_bundle(bundle, expected_column=column)
        return {**result, "r067_assumptions": bundle["r067_assumptions"],
                "r067_version": VERSION, "normative_claim": False,
                "fire_resistance_status": "not_demonstrated"}
    except MemberEvidenceInputError as exc:
        return {"status": "BLOCKED_INPUT", "reason": str(exc),
                "r067_version": VERSION, "normative_claim": False,
                "fire_resistance_status": "not_demonstrated",
                "blockers": [str(exc)]}
