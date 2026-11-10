"""SP-R.2 — numerical mesh/time campaign and independent SP Annex Zh comparison.

Tests on the same physical section do not assert *automatic* compliance:
  - three spatial meshes and two time steps estimate spatial/temporal
    sensitivity of the hot surface, centre and EVERY reinforcing bar;
  - no extrapolation of benchmark results to a different geometry;
  - optional SP Appendix Zh Table Zh.7 temperatures compare an explicit
    400×400mm all-sides 90-minute test but do not secretly calibrate
    h, emissivity, dry density or moisture to match the table.

SP §8.2.23 mathematical verification != full physical model validation.
"""
from __future__ import annotations

import copy
import math

from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat,select_sp2026_snapshot,
    sample_sp2026_temperature,SPHeatError)

VERSION="SP-R2-2026-thermal-refinement-and-Annex-Zh-v1"

# SP 2.02.05-2026, Appendix Zh Table Zh.7, printed page 122
# 400×400 mm column, 4-side standard fire, 90 minutes.
# Quarter-section origin is at the EXPOSED outer corner.
# Only selected source values are used as independent point evidence.
ZH7={
    (200.,200.):38.,
    (160.,200.):44.,
    (40.,200.):408.,
    (20.,200.):623.,
    (0.,200.):933.,
    (40.,40.):637.,
    (20.,20.):855.,
    (0.,0.):1002.,
}


def compare_sp2026_thermal_refinement(
    column,*,boundary,sample_time_minutes,
    grids=(8,12,16),time_steps=(3.,1.5),
    steel_tolerance_C=15.,concrete_tolerance_C=15.,
    centre_tolerance_C=10.):
    """Recompute the SP source model at 3 grids plus temporal refinement.

    Returns *evidence*, not source certification. The highest spatial
    mesh/time convergence check is only a necessary numerical condition.
    """
    if not isinstance(column,dict):
        raise SPHeatError("full physical source column required")
    if (not isinstance(grids,(tuple,list)) or len(grids)!=3 or
        any(type(g) is not int or g<4 or g>80 for g in grids) or
        not grids[0]<grids[1]<grids[2]):
        raise SPHeatError("three strictly increasing mesh sizes required")
    if not isinstance(time_steps,(tuple,list)) or len(time_steps)!=2:
        raise SPHeatError("two time steps required")
    dt0,dt1=(float(time_steps[0]),float(time_steps[1]))
    if not 0.25<=dt1<dt0<=30:
        raise SPHeatError("time refinement must be strictly smaller and source-valid")
    t=float(sample_time_minutes)
    if not 0.1<=t<=480.:
        raise SPHeatError("invalid evaluation time")
    c=copy.deepcopy(column)
    c["fire_minutes"]=t
    identifiers=[str(bar["id"]) for bar in c.get("bars") or []]
    if len(set(identifiers))!=len(identifiers):
        raise SPHeatError("unique actual bar identifiers required")
    if not identifiers:
        raise SPHeatError("at least one actual reinforcement bar required")

    def run(n,dt):
        data=solve_sp2026_2d_heat(c,boundary=boundary,
                cell_count_x=n,cell_count_y=n,
                max_step_minutes=dt,sample_times_minutes=[t])
        current=select_sp2026_snapshot(data,t)
        sample=lambda x,y:sample_sp2026_temperature(current,x,y)
        return {
            "grid":n,"time_step_minutes":dt,
            "centre_C":sample(c["b_mm"]/2.,c["h_mm"]/2.),
            "surface_max_C":float(data["snapshots"][-1]["boundary_max_C"]),
            "bars_C":{str(bar["id"]):sample(bar["x_mm"],bar["y_mm"])
                      for bar in c["bars"]},
            "energy_residual":data["energy_balance"]["relative_cumulative_residual"],
            "max_step_energy_residual":data["energy_balance"]["worst_step_relative_residual"]}
    spatial=[run(g,dt0) for g in grids]
    temporal=run(grids[-1],dt1)

    def delta(a,b):
        bar_differences={key:float(b["bars_C"][key]-a["bars_C"][key])
                         for key in identifiers}
        return {
            "bar_temperature_differences_C":bar_differences,
            "max_bar_delta_abs_C":max(abs(x) for x in bar_differences.values()),
            "centre_delta_abs_C":abs(b["centre_C"]-a["centre_C"]),
            "surface_delta_abs_C":abs(b["surface_max_C"]-a["surface_max_C"]),
        }
    diff0=delta(spatial[0],spatial[1])
    diff1=delta(spatial[1],spatial[2])
    temporal_diff=delta(spatial[-1],temporal)
    def inside(d):
        return (d["max_bar_delta_abs_C"]<=steel_tolerance_C and
            d["surface_delta_abs_C"]<=concrete_tolerance_C and
            d["centre_delta_abs_C"]<=centre_tolerance_C)
    within=inside(diff1) and inside(temporal_diff)
    return {
        "version":VERSION,
        "status":("WITHIN_PROVISIONAL_DISCRETIZATION_TOLERANCES"
                  if within else "REFINEMENT_NOT_YET_SUFFICIENT"),
        "time_minutes":t,
        "models":[*spatial,temporal],
        "coarse_to_intermediate":diff0,
        "intermediate_to_fine":diff1,
        "fine_temporal_refinement":temporal_diff,
        "tolerances_C":{"steel":float(steel_tolerance_C),
                        "surface":float(concrete_tolerance_C),
                        "centre":float(centre_tolerance_C)},
        "no_experimental_qualification":True,
        "external_boundary_normative_qualified":False,
        "sp2026_823_model_fully_qualified":False,
        "R_t_minutes":None,
        "normative_claim":False,
    }


def appendix_zh7_comparison(result):
    """Compare the 400×400 four-sided 90min SP model to SP Table Ж.7.

    The reference matrix provides temperatures but insufficient project
    metadata to assert equal surface exchange, initial moisture and dry
    density: numerical residuals are reference diagnostics only.
    """
    if (not isinstance(result,dict) or
        result.get("thermal_method")!="SP2026_8.2.23_FVM"):
        raise SPHeatError("SP temperature field required")
    g=result.get("grid") or {}
    if (abs(float(g.get("width_mm",0))-400.)>1e-8 or
        abs(float(g.get("height_mm",0))-400.)>1e-8 or
        set(result.get("exposed_faces") or [])!=set(
            ("left","right","bottom","top"))):
        raise SPHeatError("Annex Zh.7 is only a 400x400 four-face case")
    ref=select_sp2026_snapshot(result,90.)
    rows=[]
    for (x,y),expected in ZH7.items():
        simulated=sample_sp2026_temperature(ref,x,y)
        rows.append({
            "x_mm":x,"y_mm":y,
            "SP_table_Zh7_temperature_C":expected,
            "FVM_temperature_C":simulated,
            "difference_C":simulated-expected})
    rmse=math.sqrt(sum(row["difference_C"]**2 for row in rows)/len(rows))
    return {
        "reference":"СП 2.02.05-2026, приложение Ж, таблица Ж.7",
        "status":"DIAGNOSTIC_SOURCE_POINTS_NOT_FULLY_MATCHED_BOUNDARY",
        "pointwise":rows,
        "comparison_inputs":{
            "aggregate":result.get("material_family"),
            "dry_density_kg_m3":result.get("dry_density_kg_m3"),
            "moisture_mass_pct":result.get("moisture_mass_pct"),
            "boundary_source":result.get("external_boundary_source"),
            "convective_heat_transfer_W_m2_K":(
                (result.get("boundary_parameters") or {}).get(
                    "convection_W_m2_K")),
            "surface_emissivity":(
                (result.get("boundary_parameters") or {}).get(
                    "surface_emissivity")),
        },
        "RMSE_C":rmse,
        "max_abs_error_C":max(abs(row["difference_C"]) for row in rows),
        "source_boundary_comparability_qualified":False,
        "physical_validation_qualified":False,
        "automatic_calibration_performed":False,
        "normative_claim":False,
    }
