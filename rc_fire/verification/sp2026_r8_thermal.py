"""SP-R.8: separate the Annex K prescribed simple-section route and FVM diagnostics.

Source: SP 2.02.05-2026 §8.2.23; Annex K pp.145–146; Annex Zh pp.120–122.
Selected numerical reference observations only; no licensed source reproduction.
No fitted heat-transfer parameters or automatic regulatory acceptance.
"""
from __future__ import annotations

import math
import copy
import numpy as np
from rc_fire.thermal.normative import (
    ThermalProfile, RectangularExposure, resolve_profile, temperature_rectangle,
)
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, select_sp2026_snapshot, sample_sp2026_temperature,
)
from rc_fire.mechanics.sp2026_coupled_first_limit import (
    assess_coupled_sp5_nominal_at_time, UNKNOWN,
)

VERSION = "SP-R8-thermal-source-qualification-v1"
FACES = ("left", "right", "bottom", "top")

# (section side mm, duration min): (table number, selected anchors).
# Origin is the exposed outside corner; all values are concrete temperatures.
# Corner is separately classified: FVM reconstructs it from adjacent face samples.
REFERENCE = {
    (200, 90): ("Zh.3", ((100,100,317), (20,100,688), (0,100,945),
                         (20,20,861), (0,0,1000))),
    (400, 30): ("Zh.5", ((200,200,20), (40,200,130), (20,200,304),
                         (0,200,659), (40,40,222), (0,0,827))),
    (400, 60): ("Zh.6", ((200,200,24), (40,200,293), (20,200,507),
                         (0,200,844), (40,40,485), (0,0,933))),
    (400, 90): ("Zh.7", ((200,200,38), (40,200,408), (20,200,623),
                         (0,200,933), (40,40,637), (0,0,1002))),
    (400, 120): ("Zh.8", ((200,200,59), (40,200,495), (20,200,703),
                          (0,200,992), (40,40,740), (0,0,1046))),
}
# Suspected source anomalies, not corrected and not used in acceptance metrics.
SOURCE_ANOMALIES = (
    {"table":"Zh.4","x_mm":20,"y_mm":70,"printed_C":916,
     "transpose_C":816,"reason":"transpose mismatch"},
    {"table":"Zh.6","x_mm":80,"y_mm":160,"printed_C":95,
     "transpose_C":85,"reason":"transpose mismatch"},
    {"table":"Zh.6","x_mm":60,"y_mm":120,"printed_C":463,
     "transpose_C":463,"reason":"local nonmonotonic spike, symmetric pair"},
)

def _positive(value, label):
    x = float(value)
    if not math.isfinite(x) or x <= 0:
        raise ValueError(label + " must be finite and positive")
    return x

def annex_k_point_evidence(column, x_mm, y_mm, time_minutes, *, bar_diameter_mm=0):
    """Use existing analytical equations; never relabel them as FVM."""
    tp = column["thermal_spec"]
    profile = ThermalProfile(
        tp["concrete_family"], tp["dry_density_kg_m3"],
        tp.get("a_red_mode", "table_K1"), tp.get("moisture_mass_pct"),
    )
    coeff = resolve_profile(profile)
    exposure = RectangularExposure(column["b_mm"], column["h_mm"],
                                   tuple(tp["exposed_faces"]))
    temperature, meta = temperature_rectangle(
        exposure, coeff, time_minutes, x_mm, y_mm, bar_diameter_mm)
    valid = (bool(np.all(meta["in_one_face_0_7h"])) and
             not bool(np.any(meta["outside_approximation_C"])))
    return {
        "temperature_C": float(temperature),
        "within_implemented_K_domain": valid,
        "equation": meta["K_equation"],
        "coefficients": coeff,
        "bar_diameter_mm": float(bar_diameter_mm),
        "K11_source_wording_conflict": True,
        "K11_implemented_upper_cap": 1.0,
        "K5_distance_convention": "clear_to_bar_surface_if_bar",
        "normative_claim": False,
    }

def _metrics(rows, key):
    """Separate point classes; never pool reconstructed corners into interior."""
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"count":0, "bias_C":None,"RMSE_C":None,"max_abs_C":None}
    return {"count":len(vals), "bias_C":sum(vals)/len(vals),
            "RMSE_C":math.sqrt(sum(v*v for v in vals)/len(vals)),
            "max_abs_C":max(abs(v) for v in vals)}

def compare_annex_zh_selected(heat, column, time_minutes):
    """Matched geometry/time only; Annex Zh material/boundary metadata unknown."""
    g = heat["grid"]
    side = float(g["width_mm"])
    if (side != float(g["height_mm"]) or
        set(heat["exposed_faces"]) != set(FACES) or
        side != float(column["b_mm"]) or side != float(column["h_mm"]) or
        set(column["thermal_spec"]["exposed_faces"]) != set(FACES)):
        raise ValueError("Annex Zh reference requires matched square four-face case")
    key = (side, float(time_minutes))
    if key not in REFERENCE:
        raise ValueError("no selected Annex Zh benchmark at requested geometry/time")
    if (heat["material_family"] != column["thermal_spec"]["concrete_family"] or
        float(heat["dry_density_kg_m3"]) !=
        float(column["thermal_spec"]["dry_density_kg_m3"])):
        raise ValueError("heat and column material inventories disagree")
    table, points = REFERENCE[key]
    snap = select_sp2026_snapshot(heat, time_minutes)
    rows = []
    for x,y,expected in points:
        fvm = sample_sp2026_temperature(snap,x,y)
        k = annex_k_point_evidence(column,x,y,time_minutes)
        kind = "corner_reconstructed" if x==0 and y==0 else (
            "surface" if x==0 or y==0 else "interior")
        rows.append({"x_mm":x,"y_mm":y,"class":kind,"reference_C":expected,
                     "FVM_C":fvm,"FVM_error_C":fvm-expected,
                     "K_C":k["temperature_C"],
                     "K_error_C":k["temperature_C"]-expected if
                     k["within_implemented_K_domain"] else None,
                     "K_point_domain_valid":k["within_implemented_K_domain"]})
    groups = {}
    for kind in ("interior","surface","corner_reconstructed"):
        group = [r for r in rows if r["class"]==kind]
        groups[kind] = {"FVM":_metrics(group,"FVM_error_C"),
                        "Annex_K":_metrics(group,"K_error_C")}
    return {"version":VERSION,"reference_table":table,"time_minutes":time_minutes,
            "points":rows,"point_class_metrics":groups,
            "source_anomalies":list(SOURCE_ANOMALIES),
            "source_boundary_matched":False,"automatic_calibration_performed":False,
            "boundary_parameters":heat["boundary_parameters"],
            "energy_balance":heat["energy_balance"],
            "physical_validation_qualified":False,"normative_claim":False}

def _mechanical_state(column, heat, time, member_spec, grid, phi):
    snap = select_sp2026_snapshot(heat, time)
    try:
        result = assess_coupled_sp5_nominal_at_time(
            column,snap,member_spec,grid=grid,effective_creep_phi=phi)
        stiffness = result.get("nominal_coupled_evidence") or {}
        crit = stiffness.get("principal_Euler_Ncrit_kN")
        matrix = stiffness.get("nominal_2x2_D_kNm2")
        moment = result.get("second_order_coupled_M2_kNm")
        return {"status":result["status"],"Ncrit_kN":crit,
                "D_kNm2":matrix,"M2_kNm":moment,"grid":grid,
                "secant_available":result.get("source_secant_3x3_at_section_root")
                is not None}
    except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        return {"status":UNKNOWN,"reason":str(exc),"grid":grid,
                "Ncrit_kN":None,"D_kNm2":None,"M2_kNm":None}

def _relative_delta(a,b):
    if a is None or b is None:
        return None
    aa,bb = np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if aa.shape != bb.shape or not np.all(np.isfinite(aa)) or not np.all(np.isfinite(bb)):
        return None
    return float(np.linalg.norm(aa-bb)/max(np.linalg.norm(bb),1e-12))

def audit_heat_to_mechanics(column, member_spec, *, boundary, time_minutes,
                            thermal_grids=(8,12,16), time_steps=(2.,1.),
                            mechanical_grids=(8,12), effective_creep_phi,
                            temperature_tolerance_C=10., relative_tolerance=.03):
    """Four independent thermal solves, plus separate section quadrature refinement.

    Keep physical actions, boundary, time and bar locations fixed.
    A stable diagnostic classification does not establish a physical failure time.
    """
    t = _positive(time_minutes,"time")
    tt = _positive(temperature_tolerance_C,"temperature tolerance")
    rt = _positive(relative_tolerance,"relative tolerance")
    g0,g1,g2 = thermal_grids
    d0,d1 = time_steps
    m0,m1 = mechanical_grids
    if not (4<=g0<g1<g2<=80 and .25<=d1<d0<=30 and 4<=m0<m1):
        raise ValueError("strictly refined grids and time steps required")
    c = copy.deepcopy(column)
    c["fire_minutes"] = t
    bars = c.get("bars") or []
    ids = [str(b["id"]) for b in bars]
    if not ids or len(ids)!=len(set(ids)):
        raise ValueError("unique bar inventory required")
    runs = []
    def evaluate(n,dt,m,heat=None):
        if heat is None:
            heat = solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=n,
                    cell_count_y=n,max_step_minutes=dt,sample_times_minutes=[t])
        snap = select_sp2026_snapshot(heat,t)
        temps = {"centre":sample_sp2026_temperature(snap,c["b_mm"]/2,c["h_mm"]/2),
                 "surface_max":snap["snapshot"]["boundary_max_C"]}
        temps.update({"bar:"+str(b["id"]):sample_sp2026_temperature(
            snap,b["x_mm"],b["y_mm"]) for b in bars})
        row = {"thermal_grid":n,"max_step_min":dt,"temperatures_C":temps,
               "energy_balance":heat["energy_balance"],
               "mechanics":_mechanical_state(c,heat,t,member_spec,m,effective_creep_phi)}
        runs.append(row)
        return heat
    evaluate(g0,d0,m0)
    evaluate(g1,d0,m0)
    evaluate(g2,d0,m0)
    fine = evaluate(g2,d1,m0)
    evaluate(g2,d1,m1,fine)
    comparisons = {}
    for name,i,j in (("spatial_coarse",0,1),("spatial_fine",1,2),
                     ("temporal",2,3),("mechanical_quadrature",3,4)):
        a,b = runs[i],runs[j]
        td = max(abs(a["temperatures_C"][k]-b["temperatures_C"][k])
                 for k in a["temperatures_C"])
        am,bm = a["mechanics"],b["mechanics"]
        deltas = {key:_relative_delta(am.get(key),bm.get(key))
                  for key in ("Ncrit_kN","D_kNm2","M2_kNm")}
        passed = (td<=tt and am["status"]==bm["status"] and
                  am["status"]!=UNKNOWN and
                  all(v is not None and v<=rt for v in deltas.values()))
        comparisons[name] = {"max_point_delta_C":td,"relative_deltas":deltas,
                             "same_classification":am["status"]==bm["status"],
                             "within_numerical_tolerances":passed}
    stable = all(comparisons[k]["within_numerical_tolerances"]
                 for k in ("spatial_fine","temporal","mechanical_quadrature"))
    return {"version":VERSION,"time_minutes":t,"runs":runs,"comparisons":comparisons,
            "numerically_stable_at_tested_time":stable,
            "tolerances":{"temperature_C":tt,"relative_mechanical":rt},
            "tolerances_are_engineering_not_normative":True,
            "annex_K_to_mechanics_adapter_qualified":False,
            "thermal_physical_validation_qualified":False,
            "actual_t_R_minutes":None,"normative_claim":False}
