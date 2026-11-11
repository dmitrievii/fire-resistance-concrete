"""SP-R.4: load-proportional hot RC column resistance *evidence*.

Governing sources: СП 2.02.05-2026 §8.2.16–8.2.20, СП 5.03.01-2020
§8.1.1.5 and §§8.1.2, 8.1.6. The member has real SP-R2 heat and
SP-R1 section constitutive stresses, with two-axis P-Delta in SP-R3.

An equilibrium + checked local strain below its check-model limit is
ADMISSIBLE_IN_MODEL. A converged equilibrium with sampled strain exceeding
a specified check limit is OBSERVED_LIMIT_EXCEEDED_IN_MODEL. Loss of solver
convergence, geometric tangent, incomplete model scope or missing section
evidence is UNKNOWN, *never* proof of member failure.

This stage provides bracketed numerical demand-path resistance evidence,
NOT qualified whole-column resistance U(t) or first physical fire failure
t_R. The absence of a reliable post-peak/nonlinear hot law, full
longitudinal/imperfection validation and verified stability branch prevents
a normative fire-design result. No extrapolated resistance, no fake R90.
"""
from __future__ import annotations

import math
import numpy as np

from rc_fire.member.coupled import CoupledMemberError, solve_coupled_beam
from rc_fire.member.uls import audit_heated_member_uls
from rc_fire.member.sp2026_member import (
    _validate_spec, _snapshot_checked, _finite, SP2026MemberInputError,
    SP2026MemberFiberLaw)
from rc_fire.mechanics.sp2026_section import (
    SPSectionInputError, prepare_sp2026_section)
from rc_fire.thermal.sp2026_heat import SPHeatError
from rc_fire.materials.sp2026_fire import concrete_at_sp_fire,steel_at_sp_fire

VERSION="SP-R4-2026-load-path-and-member-uls-evidence-v1"
WITHIN="EQUILIBRATED_WITHIN_CHECKED_MODEL_LIMITS"
EXCEEDED="EQUILIBRATED_SAMPLED_STRAIN_LIMIT_EXCEEDED"
UNKNOWN="UNRESOLVED_MEMBER_STATE"


def _known_state(report):
    """Strictly classify actual member equilibrium plus complete sampled ULS.

    No iteration-limit, singular stiffness, blocked law or failed line
    search can ever be reinterpreted as a physical limit state.
    """
    if not isinstance(report, dict):
        return UNKNOWN, "member result absent"
    member=report.get("member")
    audit=report.get("uls")
    if not isinstance(member,dict) or not isinstance(audit,dict):
        return UNKNOWN, "member equilibrium or ULS audit missing"
    if member.get("status") not in ("evaluated_diagnostic",
                                     "strain_limits_exceeded_diagnostic"):
        return UNKNOWN, "beam solver did not demonstrate equilibrium"
    if audit.get("node_coverage") is not True or (
            audit.get("all_sampled_limits_resolved") is not True):
        return UNKNOWN, "not all Gauss and two-sided node strain samples resolved"
    if audit.get("gauss_count") != 3*(len(report.get("z_m") or [])-1):
        return UNKNOWN, "incomplete Gauss integration coverage"
    if audit.get("node_side_count") != 2*(len(report["z_m"])-2)+2:
        return UNKNOWN, "incomplete end/interior node checks"
    if audit.get("status") == "DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED" and (
            audit.get("exceeded_count",0)>0 or
            member.get("any_strain_limit_exceeded") is True):
        return EXCEEDED, "converged FE state exceeds a sampled section-check deformation limit"
    if (audit.get("status")=="SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS"
            and audit.get("exceeded_count")==0 and
            member.get("any_strain_limit_exceeded") is False):
        return WITHIN, "all sampled check-model strains within limits at converged equilibrium"
    return UNKNOWN,"member/ULS status inconsistent or inconclusive"


class PreparedSP2026MemberResistance:
    """Source-checked SP thermal inventory shared across load factors.

    Only the concrete/steel temperature-dependent material arrays are shared.
    Each load-factor trial gets fresh axial strain Newton hints; there is no
    accidental hysteresis induced by trial evaluation order.
    """

    def __init__(self, column, thermal_snapshot, member_spec, *,
                 grid=12, node_snapshots=None, gauss_snapshots=None):
        z,N,left,right,q,f,imperfection=_validate_spec(column,member_spec)
        t=_finite((thermal_snapshot or {}).get("fire_minutes"),
                  "fire time",positive=True)
        mode=member_spec.get("longitudinal_thermal_mode")
        if mode=="explicit_uniform_full_length":
            if member_spec.get("uniform_exposure_confirmed") is not True:
                raise SP2026MemberInputError("uniform full-length heating not confirmed")
            if node_snapshots is not None or gauss_snapshots is not None:
                raise SP2026MemberInputError("uniform heating cannot accept extra station fields")
            ref=_snapshot_checked(thermal_snapshot,t,column)
            nodes=[ref]*len(z)
            gauss=[[ref]*3 for _ in range(len(z)-1)]
        elif mode=="explicit_per_station":
            if (not isinstance(node_snapshots,(tuple,list)) or
                    len(node_snapshots)!=len(z)):
                raise SP2026MemberInputError("explicit SP thermal snapshot per node required")
            if (not isinstance(gauss_snapshots,(tuple,list)) or
                    len(gauss_snapshots)!=len(z)-1 or any(
                        not isinstance(row,(tuple,list)) or len(row)!=3
                        for row in gauss_snapshots)):
                raise SP2026MemberInputError("exactly three thermal Gauss points per element required")
            nodes=[_snapshot_checked(s,t,column) for s in node_snapshots]
            gauss=[[_snapshot_checked(s,t,column) for s in row]
                   for row in gauss_snapshots]
        else:
            raise SP2026MemberInputError("unknown member longitudinal temperature distribution")
        if type(grid) is not int or not 8<=grid<=80:
            raise SP2026MemberInputError("fibre grid must be integer 8..80")
        cache={}
        def prepared(field):
            k=id(field)
            if k not in cache:
                cache[k]=prepare_sp2026_section(column,field,grid=grid)
            return cache[k]
        self.gauss_prepared=[[prepared(s) for s in row] for row in gauss]
        self.node_prepared=[prepared(s) for s in nodes]
        self.z=z
        self.N=N
        self.left=left
        self.right=right
        self.q=q
        self.f=f
        self.imperfection=imperfection
        self.time=t
        self.member_spec=member_spec
        self.grid=grid
        self.mode=mode
        self.column=column
        self.axial_stress_relaxed_upper_bound=self._axial_strength_upper_bound()

    def _axial_strength_upper_bound(self):
        """Conservative DISCRETE axial strength upper bound, no Newton solve.

        Maximise each concrete/steel compressive stress independently,
        *ignoring* compatibility and subtracting NO displaced concrete:
        this intentionally overestimates the strength of each discretised
        section. If design N exceeds this value, even the stress-relaxed
        section cannot balance N within the admitted source strength law.
        It is NOT an experimentally qualified continuous member capacity.
        """
        samples=[]
        all_p=[("node",i,0,p) for i,p in enumerate(self.node_prepared)]
        all_p.extend(("gauss",i,j,p) for i,row in enumerate(self.gauss_prepared)
                     for j,p in enumerate(row))
        for loc,i,j,p in all_p:
            concrete_strength=np.asarray([
                concrete_at_sp_fire(p.sp_concrete,float(t),
                    normal=p.sp_concrete_normal).strength_MPa
                for t in p.theta_c],dtype=float)
            steel_strength=np.asarray([
                steel_at_sp_fire(p.sp_steel,float(t),
                    normal=p.sp_steel_normal).strength_MPa
                for t in p.theta_s],dtype=float)
            upper=1000.*(float(np.dot(p.area,concrete_strength))+
                          float(np.dot(p.bar_area,steel_strength)))
            if not math.isfinite(upper) or upper<0:
                raise SP2026MemberInputError("source temperature strength upper bound invalid")
            samples.append({"location":loc,"node_or_element":i,
                "gauss_index":j if loc=="gauss" else None,
                "axial_N_kN_upper_source_discretization":upper})
        critical=min(samples,key=lambda d:d["axial_N_kN_upper_source_discretization"])
        upper=critical["axial_N_kN_upper_source_discretization"]
        ratio=self.N/upper if upper>0. else None
        return {
            "source":"SP2026 Tables9/10 + SP5 normal strength at actual R2 field",
            "type":"stress_relaxed_section_upper_bound_no_strain_compatibility",
            "critical_station":critical,
            "source_model_N_kN_upper_bound":upper,
            "source_model_axial_utilisation_lower_bound":ratio,
            "source_model_axial_overload_if_N_above_bound":self.N>upper,
            "discretization_continuum_and_material_qualified":False,
            "normative_claim":False,
            "note":"Only valid for discretised SP source strength inventory; excludes "
                "actual constitutive compatibility and second-order amplification."}

    def evaluate_factor(self, factor):
        lam=_finite(factor,"proportional load factor")
        if lam<0.:
            raise SP2026MemberInputError("load multiplier cannot be negative")
        gauss=[[SP2026MemberFiberLaw(p) for p in row]
               for row in self.gauss_prepared]
        nodal=[SP2026MemberFiberLaw(p) for p in self.node_prepared]
        try:
            member=solve_coupled_beam(
                self.z,self.N*lam,
                law_at_gauss=lambda i,j:gauss[i][j],
                left=self.left,right=self.right,
                distributed_load_kNpm=self.q*lam,
                nodal_forces=self.f*lam,
                initial_imperfection=self.imperfection,
                max_iterations=35,tolerance=1.e-7)
            uls=audit_heated_member_uls(
                member,self.z,self.N*lam,node_laws=nodal,
                action_provenance=self.member_spec["fire_design_action_source"],
                material_provenance="SP-R1/R2/R3 SP-only heated fibres",
                temperature_time_minutes=self.time,
                axial_restraint_qualified=False,spalling_qualified=False)
            result={"member":member,"uls":uls,
                    "z_m":self.z.tolist()}
            status,reason=_known_state(result)
            critical=(uls.get("critical_sample") or {})
            ratio=critical.get("maximum_ratio")
            if ratio is not None and (
                    isinstance(ratio,bool) or
                    not math.isfinite(float(ratio))):
                ratio=None
            return {
                "load_factor":float(lam),
                "state":status,
                "reason":reason,
                "critical_model_strain_ratio":ratio,
                "critical_sample":critical if ratio is not None else None,
                "member_status":member.get("status"),
                "member_equilibrium_relative_residual":(
                    member.get("relative_equilibrium_residual")),
                "member_min_tangent_eigenvalue":(
                    member.get("tangent_min_eigenvalue")),
                "node_and_gauss_uls_status":uls.get("status"),
                "checked_gauss_count":uls.get("gauss_count"),
                "checked_node_sides":uls.get("node_side_count"),
                "normative_claim":False}
        except (CoupledMemberError,SPSectionInputError,SPHeatError,
                ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
            return {
                "load_factor":float(lam),"state":UNKNOWN,
                "reason":type(exc).__name__+": "+str(exc),
                "critical_model_strain_ratio":None,
                "critical_sample":None,
                "member_status":"EXCEPTION",
                "normative_claim":False}


def _rounded_factor(value):
    return round(float(value),12)


def bracket_model_resistance(evaluate_factor, *,
                             first_factor=0.25, step=0.25,
                             max_factor=2.0, relative_tolerance=0.005,
                             max_refinements=12):
    """Find a model-only local-strain-limit *sampled* bracket on a load ray.

    Not a mathematical proof of the first global (bifurcation, snapback)
    limit of the physical member. If a trial is UNKNOWN, do not jump over
    the gap and do not fabricate a capacity. Samples below first_factor are
    also not evaluated and a first-failure claim is not permitted.
    """
    if not callable(evaluate_factor):
        raise ValueError("evaluate_factor callback required")
    start=_finite(first_factor,"first_factor",positive=True)
    stride=_finite(step,"step",positive=True)
    stop=_finite(max_factor,"max_factor",positive=True)
    rel=_finite(relative_tolerance,"relative_tolerance",positive=True)
    if not start<=stop<=10. or stride>stop or not 0<rel<=.1:
        raise ValueError("invalid bounded resistance scan settings")
    if type(max_refinements) is not int or not 0<=max_refinements<=30:
        raise ValueError("max_refinements must be integer 0..30")
    count=int(math.ceil((stop-start)/stride))+1
    if count>80:
        raise ValueError("bounded scan exceeds 80 initial load samples")
    records=[]
    tested={}
    def take(factor):
        factor=_rounded_factor(factor)
        if factor in tested:
            return tested[factor]
        row=evaluate_factor(factor)
        if not isinstance(row,dict) or row.get("state") not in (
                WITHIN,EXCEEDED,UNKNOWN):
            raise ValueError("callback must classify an evaluated actual member state")
        d={**row,"load_factor":factor}
        records.append(d)
        tested[factor]=d
        return d
    samples=[start]
    for i in range(1,count):
        value=min(stop,start+i*stride)
        if value>samples[-1]+1.e-10:
            samples.append(value)
    if samples[-1]<stop-1.e-10:
        samples.append(stop)
    last=None
    low=high=None
    status="NO_CHECKED_MODEL_LIMIT_THROUGH_MAX_FACTOR"
    for lam in samples:
        here=take(lam)
        if here["state"]==UNKNOWN:
            status="UNRESOLVED_BEFORE_BRACKET"
            break
        if here["state"]==EXCEEDED:
            if last is None:
                status="EXCEEDED_AT_FIRST_EVALUATED_FACTOR"
            elif last["state"]==WITHIN:
                low,high=last,here
                status="OBSERVED_MODEL_STRAIN_LIMIT_BRACKET"
            else:
                status="INVALID_NONMONOTONE_MODEL_RESPONSE"
            break
        if last is not None and last["state"]==EXCEEDED:
            status="INVALID_NONMONOTONE_MODEL_RESPONSE"
            break
        last=here
    if low is not None and high is not None:
        for _ in range(max_refinements):
            if (high["load_factor"]-low["load_factor"])/high["load_factor"]<=rel:
                break
            mid=take((low["load_factor"]+high["load_factor"])/2.)
            if mid["state"]==UNKNOWN:
                status="UNRESOLVED_DURING_BRACKET_REFINEMENT"
                low=high=None
                break
            if mid["state"]==WITHIN:
                low=mid
            elif mid["state"]==EXCEEDED:
                high=mid
        if low is not None and high is not None:
            # The inverse proportional multiplier is an interpretable
            # demand/capacity index only for the declared FIXED action ray.
            # This remains an *interval*, NOT normative U_member(t).
            lo=low["load_factor"]
            hi=high["load_factor"]
            interval={
                "last_admissible_sample_factor":lo,
                "first_observed_exceedance_factor":hi,
                "relative_bracket_width":(hi-lo)/hi,
                "model_only_utilisation_interval": {
                    "lower":1./hi,
                    "upper":1./lo,
                    "interpretation":"inverse load-factor interval for sampled strain-check model only"}
            }
        else:
            interval=None
    else:
        interval=None
    return {
        "version":VERSION,"status":status,
        "scan_parameters":{"first_factor":start,"step":stride,
                           "max_factor":stop,"relative_tolerance":rel,
                           "max_refinements":max_refinements},
        "evaluations":sorted(records,key=lambda row:row["load_factor"]),
        "observed_model_resistance_bracket":interval,
        "observed_model_critical_location":(
            high.get("critical_sample") if high is not None else None),
        "unsampled_below_first_factor":True,
        "global_first_failure_or_bifurcation_qualified":False,
        "U_member_t":None,
        "R_t_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "normative_claim":False,
        "qualification_blockers":[
            "SP5_COMPLETE_HOT_NONLINEAR_STIFFNESS_AND_STRAIN_HISTORY_NOT_QUALIFIED",
            "FIRST_GLOBAL_STABILITY_AND_POSTPEAK_BRANCH_NOT_QUALIFIED",
            "SP2026_THERMAL_BOUNDARIES_SPALLING_NOT_QUALIFIED",
            "SAMPLED_SP5_CHECK_BRANCH_NOT_FULL_MEMBER_ULS",
            "UNSAMPLED_STRAIN_OR_CAPACITY_BRANCH_BELOW_FIRST_FACTOR"]}


def _min_eccentricity_audit(column,reference_N):
    """SP5 §8.1.1.5: e0 >= max(h/30, 20 mm) in relevant bend plane.

    Report the missing input reconciliation; never silently add a second
    set of moments to already-design fire action vectors.
    """
    b=_finite(column.get("b_mm"),"b_mm",positive=True)
    h=_finite(column.get("h_mm"),"h_mm",positive=True)
    e_x=max(h/30.,20.)
    e_y=max(b/30.,20.)
    return {
        "source":"СП 5.03.01-2020 §8.1.1.5",
        "minimum_eccentricity_about_x_mm":e_x,
        "minimum_eccentricity_about_y_mm":e_y,
        "corresponding_N_e_x_kNm":reference_N*e_x/1000.,
        "corresponding_N_e_y_kNm":reference_N*e_y/1000.,
        "already_included_in_action_and_imperfection_input_verified":False,
        "notice":"Eccentricity must be accounted for consistently; no automatic M is introduced."}


def evaluate_sp2026_member_resistance(column,thermal_snapshot,member_spec, *,
                                      grid=12,node_snapshots=None,
                                      gauss_snapshots=None,
                                      first_factor=.25,step=.25,
                                      max_factor=2.,relative_tolerance=.005,
                                      max_refinements=12):
    """Prepared actual SP member + source-consistent proportional action scan."""
    case=PreparedSP2026MemberResistance(
        column,thermal_snapshot,member_spec,grid=grid,
        node_snapshots=node_snapshots,gauss_snapshots=gauss_snapshots)
    result=bracket_model_resistance(
        case.evaluate_factor,first_factor=first_factor,step=step,
        max_factor=max_factor,relative_tolerance=relative_tolerance,
        max_refinements=max_refinements)
    # The required load state must be separately evaluated, even if the
    # coarse load scan terminates at a lower-factor exceeded sample.
    required=case.evaluate_factor(1.)
    return {**result,"fire_time_minutes":case.time,
        "member_model":"SP2026_SP-R2_HEAT_SP-R1_FIBRE_SP-R3_TWO_AXIS_PDELTA",
        "exposure_mode":case.mode,"beam_node_count":len(case.z),
        "temperature_station_count":len(case.node_prepared)+3*len(case.gauss_prepared),
        "reference_design_actions":{
            "N_fi_kN":float(case.N),
            "distributed_load_kNpm":case.q.tolist(),
            "nodal_forces":case.f.tolist(),
            "load_path":"all applied actions proportional; geometric imperfection unscaled",
            "source":member_spec.get("fire_design_action_source")},
        "at_declared_design_actions":required,
        "minimum_eccentricity_check":_min_eccentricity_audit(column,case.N),
        "stress_relaxed_axial_strength_upper_bound":case.axial_stress_relaxed_upper_bound,
        "actual_R_d_member":None,"actual_U_member_t":None}


def scan_sp2026_resistance_time_history(
        column,heat_result,member_spec,times_minutes, *,
        grid=12,first_factor=.25,step=.25,max_factor=2.,
        relative_tolerance=.005,max_refinements=12):
    """At independently stored SP-R2 times evaluate the *same* physical column.

    Each time is an entirely new thermal/mechanical solution. No interpolation
    in time, material-history extrapolation, zero-tail discontinuity smoothing,
    or conversion of nominal-demand nonconvergence into fire failure.
    """
    from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
    if not isinstance(heat_result,dict) or (
            heat_result.get("thermal_method")!="SP2026_8.2.23_FVM"):
        raise SP2026MemberInputError("SP-R4 fire history requires independent SP-R2 heat")
    if not isinstance(times_minutes,(list,tuple)) or not 1<=len(times_minutes)<=12:
        raise SP2026MemberInputError("SP-R4 history requires 1..12 specified times")
    times=[_finite(t,"fire history time",positive=True) for t in times_minutes]
    if any(b<=a for a,b in zip(times,times[1:])):
        raise SP2026MemberInputError("SP-R4 fire history times must strictly increase")
    if member_spec.get("longitudinal_thermal_mode")!="explicit_uniform_full_length":
        raise SP2026MemberInputError(
            "SP-R4 history from single 2D source requires affirmed uniform heating")
    rows=[]
    for t in times:
        selected=select_sp2026_snapshot(heat_result,t)
        evidence=evaluate_sp2026_member_resistance(
            column,selected,member_spec,grid=grid,
            first_factor=first_factor,step=step,max_factor=max_factor,
            relative_tolerance=relative_tolerance,
            max_refinements=max_refinements)
        bracket=evidence.get("observed_model_resistance_bracket")
        rows.append({
            "time_minutes":t,
            "model_scan_status":evidence["status"],
            "nominal_fire_action_state":evidence["at_declared_design_actions"]["state"],
            "nominal_fire_action_critical_strain_ratio":(
                evidence["at_declared_design_actions"].get(
                    "critical_model_strain_ratio")),
            "model_load_factor_low":(
                bracket["last_admissible_sample_factor"] if bracket else None),
            "model_load_factor_high":(
                bracket["first_observed_exceedance_factor"] if bracket else None),
            "model_only_utilisation_interval":(
                bracket["model_only_utilisation_interval"] if bracket else None),
            "unknown_load_factors":[
                r["load_factor"] for r in evidence["evaluations"]
                if r["state"]==UNKNOWN],
            "model_critical_location":evidence.get(
                "observed_model_critical_location"),
            "source_model_N_kN_upper_bound":evidence[
                "stress_relaxed_axial_strength_upper_bound"][
                    "source_model_N_kN_upper_bound"],
            "source_model_axial_utilisation_lower_bound":evidence[
                "stress_relaxed_axial_strength_upper_bound"][
                    "source_model_axial_utilisation_lower_bound"],
            "normative_claim":False})
    # This is an OBSERVED transition in the sampled model at lambda=1,
    # not first failure time; an unobserved failure may predate both.
    observed=[]
    for a,b in zip(rows,rows[1:]):
        if (a["nominal_fire_action_state"]==WITHIN and
                b["nominal_fire_action_state"]==EXCEEDED):
            observed.append({
                "last_observed_model_within_minutes":a["time_minutes"],
                "first_observed_model_exceeded_minutes":b["time_minutes"]})
    return {
        "version":VERSION,
        "status":"SAMPLED_MODEL_HISTORY_WITH_UNRESOLVED_STATES"
            if any(row["nominal_fire_action_state"]==UNKNOWN
                   for row in rows)
            else "SAMPLED_MODEL_HISTORY_EVALUATED",
        "samples":rows,
        "observed_model_nominal_action_strain_transitions":observed,
        "temperature_history_source":"SP2026_8.2.23_FVM_STORED_TIMES_ONLY",
        "no_temporal_interpolation":True,
        "U_t":None,"t_R":None,"R_t_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED","normative_claim":False,
        "interpretation":"Sampled model strain and conditional resistance envelope history; "
            "no verified continuous first loss of load-bearing capacity."}
