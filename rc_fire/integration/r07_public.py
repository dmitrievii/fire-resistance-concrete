"""R0.7 public calculation facade: one input, one fire-resistance assessment.

The installed advanced TKP heat/fibre modules calculate section equilibrium,
NOT the normative first loss of *member* carrying capacity. This API
deliberately does not manufacture an R(t) from Newton nonconvergence, an
isolated section strain, or the fact the user selected a required duration.

Numerical outputs include actual thermal/fibre histories and observed
transition intervals. The regulatory verdict is always NOT_ESTABLISHED until
a validated full-member fire ultimate limit state is integrated and qualified.
A later engine may add the verified member criterion without changing the UI.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from multicolumn_r05.project_model import validate_column
from rc_fire.integration.r069d3 import evaluate_tkp_thermal_mechanical_history
from rc_fire.thermal.tkp_heat import reference_annex_a_boundary
from rc_fire.mechanics.action_capacity import WITHIN, EXCEEDED, UNKNOWN

VERSION="R0.7-public-fire-workflow-v1"
SUPPORTED_R_MINUTES=(30,45,60,90,120,150,180)


class PublicFireInputError(ValueError):
    pass


def _positive(value,name):
    if isinstance(value,bool):
        raise PublicFireInputError(f"{name}: numeric input required")
    try: out=float(value)
    except (TypeError,ValueError) as exc:
        raise PublicFireInputError(f"{name}: numeric input required") from exc
    if not math.isfinite(out) or out<=0:
        raise PublicFireInputError(f"{name}: positive finite value required")
    return out


def _input_preflight(c:dict,*,required_minutes,steel_route,ductility_class,
                     moisture_mass_pct):
    if not isinstance(c,dict):
        raise PublicFireInputError("column dictionary required")
    required=_positive(required_minutes,"Rrequired")
    if required>120.:
        # Current search to 2 x Rrequired would exceed the existing 240-min
        # source/thermal calculator horizon. Do NOT silently shorten scan.
        raise PublicFireInputError(
            "The current integrated time history supports Rrequired<=120 min. "
            "R150/R180 require an extended validated time solver.")
    if steel_route not in ("hot_rolled","cold_worked"):
        raise PublicFireInputError(
            "Actual rebar production route (hot_rolled/cold_worked) is required")
    if ductility_class not in ("A","B","C"):
        raise PublicFireInputError("Actual reinforcing ductility A/B/C is required")
    w=_positive(moisture_mass_pct,"concrete gravimetric moisture %")
    if w>3.:
        raise PublicFireInputError(
            "Thermal heat-capacity moisture peak is only tabulated for <=3%")
    if not isinstance(c.get("bars"),list) or len(c["bars"])<4:
        raise PublicFireInputError("at least 4 real reinforcement bars required")
    if not isinstance(c.get("sections"),list) or not c["sections"]:
        raise PublicFireInputError("at least one load section required")
    for s in c["sections"]:
        if any(s.get(k) is None for k in ("N_kN","Mx_kNm","My_kNm")):
            raise PublicFireInputError(
                "N, Mx, My are all required as ALREADY FIRE-DESIGN actions")
        if _positive(s["N_kN"],f"{s.get('id')}.N")<=0:
            raise PublicFireInputError("axial force must be positive")
        for k in ("Mx_kNm","My_kNm"):
            try: v=float(s[k])
            except (ValueError,TypeError) as exc:raise PublicFireInputError(
                k+": finite numeric moment required") from exc
            if not math.isfinite(v):raise PublicFireInputError(k+": finite moment required")
    if not (c.get("thermal_spec") or {}).get("concrete_family"):
        raise PublicFireInputError("concrete aggregate family required")
    if (c.get("thermal_spec") or {}).get("dry_density_kg_m3") is None:
        raise PublicFireInputError("actual dry density required")
    if not (c.get("material_spec") or {}).get("concrete",{}).get("consistency"):
        raise PublicFireInputError("concrete mix consistency required for SP 5.03.01 Table 6.3")
    if not (c.get("annex_l_spec") or {}).get("coarse_aggregate_volume_pct"):
        raise PublicFireInputError("coarse aggregate fraction required for material classification")
    # Respect all existing canonical input validation without carrying tests
    # into the public interface.
    issues=validate_column(c)
    if issues:
        raise PublicFireInputError("; ".join(issues))


def fire_assessment(column:dict,*,required_minutes:float,
    steel_route:str,ductility_class:str,moisture_mass_pct:float,
    grid:int=12,dt_minutes:float=5.,
    assess_member:bool=False)->dict[str,Any]:
    """Return numerical evidence AND independently qualified conclusion.

    Never mislabel an observed first-order strain-limit transition as
    full-member fire collapse. True t_R remains None if unqualified.
    """
    _input_preflight(column,required_minutes=required_minutes,
        steel_route=steel_route,ductility_class=ductility_class,
        moisture_mass_pct=moisture_mass_pct)
    required=float(required_minutes)
    if type(grid) is not int or grid not in (8,12,16,24,32):
        raise PublicFireInputError("mesh grid must be one of 8/12/16/24/32")
    dt=_positive(dt_minutes,"time step")
    if dt<.25 or dt>10:
        raise PublicFireInputError("time step out of supported range [.25,10] min")
    # Exact multiple sampling ensures Rrequired itself is always a mechanical
    # sample, not interpolated between two unrelated Newton roots.
    horizon=required*2.
    step=required/5.
    c=copy.deepcopy(column)
    c["fire_minutes"]=horizon
    bound=reference_annex_a_boundary(moisture_mass_pct=float(moisture_mass_pct))
    history=evaluate_tkp_thermal_mechanical_history(c,
        boundary=bound,production_route=steel_route,
        ductility_class=ductility_class,
        cell_count=grid,fibre_grid=grid,
        max_step_minutes=dt,step_minutes=step,
        max_factor=1.,factor_step=1.,max_bisection=0,
        include_member=bool(assess_member),
        refine_strain_transition=False)
    points=history.get("samples") or []
    exact=[p for p in points if abs(p["time_minutes"]-required)<1e-7]
    if len(exact)!=1:
        raise RuntimeError("Rrequired not evaluated at its exact fire time")
    at=exact[0]
    first=history.get("observed_section_strain_transition") or {}
    statuses=[p.get("reference_classification",UNKNOWN) for p in points]
    # Never pass an unknown/unstable point just because earlier times were
    # within strain limits. Equilibrium != normative carrying capacity.
    all_observed_within=all(s==WITHIN for s in statuses)
    any_unknown=any(s==UNKNOWN for s in statuses)
    any_exceeded=any(s==EXCEEDED for s in statuses)
    member=(at.get("member") or {}) if assess_member else {}
    blockers=[
       "FULL_COLUMN_FIRE_ULS_NOT_VALIDATED_TKP_4_3_4",
       "TEMPERATURE_AND_MECHANICAL_MESH_CONVERGENCE_NOT_ESTABLISHED",
       "SPALLING_ANNEX_L_OR_TKP_4_5_NOT_INDEPENDENTLY_CLOSED",
       "LONGITUDINAL_SUPPORT_RESTRAINT_AND_ACTION_PATH_MUST_BE_QUALIFIED",
       "OBSERVED_SECTION_STRAIN_IS_NOT_PHYSICAL_MEMBER_COLLAPSE",
    ]
    if at.get("status")!="FVM_TKP_FIBRES_NUMERICAL_DIAGNOSTIC":
        blockers.append("REQUIRED_TIME_SECTION_EQUILIBRIUM_NOT_SOLVED")
    if not assess_member or member.get("status")!="MEMBER_DIAGNOSTIC_EQUILIBRATED":
        blockers.append("FULL_MEMBER_EQUILIBRIUM_NOT_SOLVED")
    if any_unknown:blockers.append("UNKNOWN_SAMPLED_MECHANICAL_STATES")
    report={
      "release":VERSION,"status":"NUMERICAL_CALCULATION_COMPLETE",
      "required_rating_minutes":required,
      "calculated_member_failure_time_minutes":None,
      "R_t_minutes":None,
      "normative_R_at_least_required":None,
      "regulatory_result":"NOT_ESTABLISHED",
      "rating_matches_requirement":None,
      "observed_strain_limit_transition":first.get(
            "observed_within_to_exceeded_intervals",[]),
      "first_observed_section_strain_exceedance_minutes":first.get(
            "first_observed_strain_exceedance_minutes"),
      "numerical_section_at_required_time":at.get("reference_classification",UNKNOWN),
      "numerical_section_status_at_required_time":at.get("status"),
      "numerical_section_all_times_within":all_observed_within,
      "numerical_some_times_unknown":any_unknown,
      "numerical_some_times_exceeded":any_exceeded,
      "required_time_temperatures":{
          "gas_C":at.get("T_gas_C"),
          "concrete_surface_max_C":at.get("T_concrete_boundary_max_C"),
          "concrete_centre_C":at.get("T_concrete_center_C"),
          "bars_C":at.get("T_reinforcement_C")},
      "energy_balance":history.get("thermal_energy_balance"),
      "timeline":[{
          "minute":p["time_minutes"],
          "gas_C":p.get("T_gas_C"),
          "concrete_surface_C":p.get("T_concrete_boundary_max_C"),
          "concrete_centre_C":p.get("T_concrete_center_C"),
          "section_classification":p.get("reference_classification"),
          "section_solver_status":p.get("status"),
          "member_status":(p.get("member") or {}).get("status")}
          for p in points],
      "materials":{
          "concrete":column.get("concrete"),
          "density_kg_m3":column.get("thermal_spec",{}).get("dry_density_kg_m3"),
          "aggregate":column.get("thermal_spec",{}).get("concrete_family"),
          "steel_grade":column.get("steel_grade"),
          "steel_route":steel_route,
          "steel_ductility":ductility_class,
          "moisture_mass_pct":float(moisture_mass_pct)},
      "fire_design_actions":[
          {k:s.get(k) for k in ("id","z_m","N_kN","Mx_kNm","My_kNm")}
          for s in column["sections"]],
      "method_sources":[
          "ТКП EN 1992-1-2-2009 §3.2, §3.3, §4.3 and Belarus National Annex",
          "СП 2.02.05-2026 standard fire, formula (3)",
          "СП 5.03.01-2020 room-temperature material catalog"],
      "remaining_normative_blockers":blockers,
      "full_internal_audit":history,
    }
    return report
