"""SP-R8B analytical Annex K field: no FVM impersonation or silent fallback.

Source: SP 2.02.05-2026 §8.2.23, K.1–K.12.
The K.11 upper cap is a documented resolution of contradictory wording;
K.5 clear/centre alternatives are explicit. No physical R certification.
"""
from __future__ import annotations
import math
from rc_fire.thermal.normative import (
    ThermalError, ThermalProfile, RectangularExposure,
    resolve_profile, temperature_rectangle,
)

ANNEX_K_METHOD = "SP2026_ANNEX_K_ANALYTICAL"
VERSION = "SP-R8B-annex-K-field-v1"

def _inputs(column):
    tp=column["thermal_spec"]
    profile=ThermalProfile(
        tp["concrete_family"],float(tp["dry_density_kg_m3"]),
        tp.get("a_red_mode","table_K1"),tp.get("moisture_mass_pct"))
    exposure=RectangularExposure(float(column["b_mm"]),float(column["h_mm"]),
                                 tuple(tp["exposed_faces"]))
    exposure.validate()
    coeff=resolve_profile(profile)
    if profile.family not in ("siliceous","calcareous"):
        raise ThermalError("SP2026 Table9 heavy concrete required")
    return exposure,coeff

def _point(exposure,coeff,time,x,y,diameter,convention):
    val,meta=temperature_rectangle(exposure,coeff,time,x,y,diameter,
                                    bar_distance_convention=convention)
    if not bool(meta["in_one_face_0_7h"]):
        raise ThermalError("K.6 x > 0.7h: full-section analytical field unavailable")
    if bool(meta["outside_approximation_C"]) or not math.isfinite(float(val)):
        raise ThermalError("Annex K temperature outside implemented source domain")
    return float(val)

def build_annex_k_snapshot(column,time_minutes,*,bar_distance_convention="clear"):
    """Build analytical snapshot; sample each fibre directly from equations."""
    t=float(time_minutes)
    if not math.isfinite(t) or not 0<=t<=float(column["fire_minutes"]):
        raise ThermalError("time outside declared column duration")
    if bar_distance_convention not in ("clear","centre"):
        raise ThermalError("K.5 distance convention must be clear or centre")
    ex,coeff=_inputs(column)
    b,h=ex.b_mm,ex.h_mm
    # The mechanics requires the entire section, including boundaries.
    # A one-face K.6 model cannot supply the out-of-domain back region.
    boundary=[(0,0),(b,0),(0,h),(b,h),(b/2,0),(b/2,h),(0,h/2),(b,h/2)]
    values=[_point(ex,coeff,t,x,y,0,bar_distance_convention) for x,y in boundary]
    return {"version":VERSION,"status":"evaluated_annex_k_conditional",
            "thermal_method":ANNEX_K_METHOD,"fire_minutes":t,
            "material_family":coeff["material_family"],
            "exposed_faces":list(ex.faces),
            "grid":{"width_mm":b,"height_mm":h},
            "snapshot":{"time_minutes":t,"boundary_max_C":max(values)},
            "annex_k_coefficients":coeff,
            "annex_k_provenance":{
                "source":"SP 2.02.05-2026 §8.2.23, Annex K K.1–K.12",
                "K11_upper_cap_interpretation":True,
                "K5_distance_convention":bar_distance_convention,
                "source_wording_clarified_by_authority":False,
                "external_h_epsilon_used":False,
                "density_interpolation":coeff["K2_density_status"],
                "no_critical_isotherm_used":True},
            "normative_claim":False,"R_t_minutes":None}

def validate_annex_k_snapshot(column,field):
    """Reject changed source geometry, profile, time or provenance."""
    if field.get("thermal_method")!=ANNEX_K_METHOD:
        raise ThermalError("actual Annex K field required")
    convention=field["annex_k_provenance"]["K5_distance_convention"]
    expected=build_annex_k_snapshot(column,field["snapshot"]["time_minutes"],
                                   bar_distance_convention=convention)
    for key in ("status","version","grid","material_family","exposed_faces",
                "annex_k_coefficients","annex_k_provenance","snapshot","fire_minutes"):
        if expected[key]!=field.get(key):
            raise ThermalError("Annex K snapshot does not match source column: "+key)

def sample_annex_k_temperature(field,x_mm,y_mm,*,bar_diameter_mm=0):
    if field.get("thermal_method")!=ANNEX_K_METHOD:
        raise ThermalError("no relabelled FVM/legacy field allowed")
    g=field["grid"]
    ex=RectangularExposure(g["width_mm"],g["height_mm"],
                           tuple(field["exposed_faces"]))
    return _point(ex,field["annex_k_coefficients"],
                  field["snapshot"]["time_minutes"],x_mm,y_mm,
                  bar_diameter_mm,field["annex_k_provenance"]["K5_distance_convention"])
