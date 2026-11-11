"""SP-R.2: couple SP 2026 nonlinear fibres to time-matched SP thermal grid.

The primary transport path uses SP Appendix K.1 material properties
under SP §8.2.23. An older TKP thermal field may still be evaluated
in a separately labelled diagnostic legacy compatibility mode.
The boundary coefficients, moisture transport and mesh convergence
are NOT yet qualified for a normative R(t). The mechanical constitutive
law is independent: SP2026 Tables9/10 + SP5 §6.1.5.4/§6.2.2.13.

A first-order heated SECTION is not a full heated COLUMN or R(t).
"""
from __future__ import annotations

import math
import numpy as np

from rc_fire.materials.normative import (
    ConcreteMix,Reinforcement,resolve_materials)
from rc_fire.materials.sp2026_fire import (
    SPFireMaterialError,concrete_at_sp_fire,steel_at_sp_fire,
    concrete_stress_sp,steel_stress_sp,concrete_free_thermal_strain_sp,
    steel_free_thermal_strain_sp,qualification_status)
from rc_fire.mechanics.tkp_thermomechanical_fibres import (
    TKPPreparedFibres)
from rc_fire.thermal.tkp_heat import sample_tkp_temperature
from rc_fire.thermal.sp2026_heat import sample_sp2026_temperature

VERSION="SP-R2-2026-heated-section-fibre-coupling-v2"


class SPSectionInputError(ValueError):
    pass


def _positive(value,name):
    if isinstance(value,bool):
        raise SPSectionInputError(name+": finite positive number required")
    try: out=float(value)
    except (ValueError,TypeError) as exc:
        raise SPSectionInputError(name+": positive number required") from exc
    if not math.isfinite(out) or out<=0:
        raise SPSectionInputError(name+": finite positive number required")
    return out


class SPPreparedSection(TKPPreparedFibres):
    """SP concrete/steel σ-ε, first-order compatible N-Mx-My integration.

    Reuse proven source-neutral Newton *equilibrium driver* and section
    coordinates, but NOT the TKP concrete/steel stress and strain laws.
    The computed model-only state remains NOT normative R(t).
    """
    def force_and_tangent(self,unknowns,*,include_maps=False):
        q=np.asarray(unknowns,dtype=float)
        if q.shape!=(3,) or not np.all(np.isfinite(q)):
            raise SPSectionInputError("finite [e0,kx,ky] required")
        e0,kx,ky=q
        ec=e0+kx*self.v+ky*self.u+self.eps_th_c
        eb=e0+kx*self.bar_v+ky*self.bar_u+self.eps_th_cb
        es=e0+kx*self.bar_v+ky*self.bar_u+self.eps_th_s
        concrete=self.sp_concrete
        steel=self.sp_steel
        c_norm=self.sp_concrete_normal
        s_norm=self.sp_steel_normal
        sc=np.zeros(len(ec));tc=np.zeros(len(ec))
        sb=np.zeros(len(eb));tb=np.zeros(len(eb))
        ss=np.zeros(len(es));ts=np.zeros(len(es))
        # Distinct SP5 §6.1.5.2 full-curve research branch. Defaults stay
        # source-identical to the qualified SP-R1 §6.1.5.4 section law.
        concrete_law=getattr(self,"sp_concrete_stress_fn",concrete_stress_sp)
        steel_law=getattr(self,"sp_steel_stress_fn",steel_stress_sp)
        model_mode=getattr(self,"sp_constitutive_mode",
                           "SP5_6_1_5_4_SECTION_CHECK")
        max_ratio=0.
        active=0
        for i,(strain,T) in enumerate(zip(ec,self.theta_c)):
            sc[i],tc[i],eps_u,material=concrete_law(
                float(strain),float(T),concrete,c_norm)
            if eps_u is not None:
                active+=1
                max_ratio=max(max_ratio,max(0.,float(strain))/eps_u)
        for i,(strain,T) in enumerate(zip(eb,self.theta_cb)):
            sb[i],tb[i],eps_u,material=concrete_law(
                float(strain),float(T),concrete,c_norm)
            if eps_u is not None:
                max_ratio=max(max_ratio,max(0.,float(strain))/eps_u)
        for i,(strain,T) in enumerate(zip(es,self.theta_s)):
            ss[i],ts[i],material=steel_law(
                float(strain),float(T),steel,s_norm)
        # Check actual hot boundary locations as well as fibre *centres*.
        # The governing surface may crush before any centre sample does.
        # Exact finite boundary samples do NOT prove a continuous maximum.
        fibre_ratio=max_ratio
        boundary_ratio=0.
        for j,T in enumerate(self.sp_boundary_temperature):
            eps=(e0+kx*self.sp_boundary_v[j]+ky*self.sp_boundary_u[j]
                 +self.sp_boundary_free_strain[j])
            _,_,eps_u,_=concrete_law(
                float(eps),float(T),concrete,c_norm)
            if eps_u is not None:
                boundary_ratio=max(boundary_ratio,max(0.,float(eps))/eps_u)
        max_ratio=max(max_ratio,boundary_ratio)
        # SP 5.03.01-2020 §8.1.2.1, *section verification* branch:
        # tensile reinforcing steel has the check limit epsilon_s <=10 per
        # mille (compression-positive convention => tension negative).
        # This is not an eps_ud validation of a full nonlinear analysis,
        # and is not used to infer member fire endurance.
        steel_tensile_strain=max(0.,-float(np.min(es)))
        # SP5 §8.1.2 section-check 10‰ is NOT the steel limit of the
        # full §6.1.5.2 nonlinear structural branch. Without certified
        # hot εud no FULL-branch member ULS may be declared "within".
        if model_mode=="SP5_6_1_5_4_SECTION_CHECK":
            steel_check_ratio=steel_tensile_strain/.010
            max_ratio=max(max_ratio,steel_check_ratio)
        else:
            steel_check_ratio=None
        # Identical force conventions, shapes and units to the existing
        # 3-DOF section equilibrium. Gross concrete plus steel stress
        # minus displaced-concrete stress at each physical bar.
        yc=self.y-self.h_m/2.;xc=self.x-self.b_m/2.
        yb=self.bar_y-self.h_m/2.;xb=self.bar_x-self.b_m/2.
        shape_c=np.stack((np.ones(len(ec)),self.v,self.u),axis=0)
        shape_s=np.stack((np.ones(len(es)),self.bar_v,self.bar_u),axis=0)
        mc=np.stack((np.ones(len(ec)),yc,xc),axis=0)
        ms=np.stack((np.ones(len(es)),yb,xb),axis=0)
        A=1000.*self.area
        B=1000.*self.bar_area
        F=mc@(A*sc)+ms@(B*(ss-sb))
        J=(mc*(A*tc)[None,:])@shape_c.T+(
            ms*(B*(ts-tb))[None,:])@shape_s.T
        status=(bool(max_ratio<=1.+1e-12)
                if model_mode=="SP5_6_1_5_4_SECTION_CHECK" else None)
        meta={
            "model":VERSION,
            "constitutive_mode":model_mode,
            "temperature_dependent_peak_and_ultimate_strain_qualified":False,
            "source":self.source,
            "normative_claim":False,
            "critical_mechanical_strain_ratio":float(max_ratio),
            "model_only_strain_limits_satisfied":status,
            "strain_limits_satisfied":status,
            "zero_strength_concrete_fibre_count":int(
                np.count_nonzero(self.theta_c>800.)),
            "zero_strength_concrete_displaced_fibre_count":int(
                np.count_nonzero(self.theta_cb>800.)),
            "source_steel_temperatures_all_le800":bool(
                np.all(self.theta_s<=800.)),
            "steel_check_tension_strain_limit":.010,
            "steel_check_tension_ratio":float(steel_check_ratio),
            "steel_check_source":(
                "СП 5.03.01-2020 §8.1.2.1 section-check 10‰"
                if steel_check_ratio is not None
                else "NOT_APPLICABLE_FULL_NONLINEAR_STEEL_EPS_UD_UNQUALIFIED"),
            "steel_eps_ud_full_nonlinear_analysis_qualified":False,
            "full_hot_constitutive_physical_qualification":False,
            "model_uls_evidence_complete":status is not None,
            "max_steel_tensile_strain":steel_tensile_strain,
            "maximum_concrete_fibre_ratio":float(fibre_ratio),
            "maximum_concrete_boundary_ratio":float(boundary_ratio),
            "concrete_boundary_check_points":len(self.sp_boundary_temperature),
            "concrete_boundary_continuum_qualified":False,
            "concrete_active_fibre_count":active,
            "max_concrete_temperature_C":float(np.max(self.theta_c)),
            "max_steel_temperature_C":float(np.max(self.theta_s)),
            "user_zero_tail_not_SP_tabulated":True,
            "member_second_order_and_stability_not_solved":True,
            "thermal_SP_823_convergence_not_validated":True,
            "steel_ultimate_strain_not_independently_qualified":True,
        }
        if include_maps:
            meta["map"]={
                "concrete_stress_MPa":sc.tolist(),
                "steel_stress_MPa":ss.tolist(),
                "concrete_strain":ec.tolist(),
                "steel_strain":es.tolist()}
        return np.asarray(F,dtype=float),np.asarray(J,dtype=float),meta


def prepare_sp2026_section(column,thermal_snapshot,*,grid=12):
    """SP fibre inventory sampled ONLY from the provided FVM temperature field.

    SP Appendix K.1-based FVM is the primary source; the TKP field
    remains available only as an explicitly segregated legacy diagnostic.
    No Annex K critical isotherm substitution or steel extrapolation.
    """
    if not isinstance(column,dict) or not isinstance(thermal_snapshot,dict):
        raise SPSectionInputError("column and explicit thermal snapshot required")
    method=thermal_snapshot.get("thermal_method")
    if method not in ("SP2026_8.2.23_FVM","TKP_4.3.2_FVM") or not isinstance(
        thermal_snapshot.get("snapshot"),dict):
        raise SPSectionInputError("time-matched SP or legacy TKP FVM snapshot required")
    expected_status=("evaluated_sp2026_thermal_diagnostic"
                     if method=="SP2026_8.2.23_FVM" else "evaluated_tkp_diagnostic")
    if thermal_snapshot.get("status")!=expected_status:
        raise SPSectionInputError("source thermal solution not evaluated")
    temperature_at=(sample_sp2026_temperature if method=="SP2026_8.2.23_FVM"
                    else sample_tkp_temperature)
    if type(grid) is not int or not 8<=grid<=80:
        raise SPSectionInputError("mechanical fibre grid integer 8..80 required")
    mat=resolve_materials(column)
    if mat.get("status")!="resolved_for_property_lookup":
        raise SPSectionInputError("SP5 normal materials unresolved: "+
                                  str(mat.get("issues")))
    aggregate=mat["fire_family"]
    if aggregate not in ("siliceous","calcareous"):
        raise SPSectionInputError("SP Table9 beta applies to ordinary heavy concrete only")
    cb=mat["concrete"];ss=mat["steel"]
    # Use the exact catalog normal-temperature numbers. No re-labelling
    # of an assumed Ecm as measured, and no reusing TKP fire factors.
    concrete=ConcreteMix(column["concrete"],aggregate_family=aggregate)
    steel=Reinforcement(grade=column.get("steel_grade","S500"),
        **((column.get("material_spec") or {}).get("steel") or {}))
    width=_positive(column["b_mm"],"b_mm")/1000.
    height=_positive(column["h_mm"],"h_mm")/1000.
    field=thermal_snapshot
    g=field["grid"]
    if abs(float(g["width_mm"])-width*1000.)>1e-6 or abs(
        float(g["height_mm"])-height*1000.)>1e-6:
        raise SPSectionInputError("thermal and SP mechanical cross-section geometry mismatch")
    if field.get("material_family")!=aggregate:
        raise SPSectionInputError("SP concrete aggregate differs from thermal solution")
    t=float(field["snapshot"]["time_minutes"])
    if not 0<t<=float(column.get("fire_minutes",t))+1e-8:
        raise SPSectionInputError("temperature snapshot outside source fire duration")
    xx=(np.arange(grid)+.5)*width/grid
    yy=(np.arange(grid)+.5)*height/grid
    X,Y=np.meshgrid(xx,yy,indexing="xy")
    temps=np.asarray([temperature_at(field,float(x*1000.),float(y*1000.))
        for x,y in zip(X.ravel(),Y.ravel())],dtype=float)
    bx=[];by=[];As=[];ts=[];tcb=[];ids=[]
    for i,bar in enumerate(column.get("bars") or []):
        x=_positive(bar.get("x_mm"),"bar.x")/1000.
        y=_positive(bar.get("y_mm"),"bar.y")/1000.
        d=_positive(bar.get("diameter_mm"),"bar.d")/1000.
        if not d/2.<x<width-d/2. or not d/2.<y<height-d/2.:
            raise SPSectionInputError("bar outside section; check physical cover")
        temperature=temperature_at(field,x*1000.,y*1000.)
        # Explicit steel >800 fail-closed. Concrete >800 => 0 stress.
        steel_at_sp_fire(steel,temperature,normal=ss)
        ids.append(str(bar["id"]))
        bx.append(x);by.append(y)
        As.append(math.pi*(d/2.)**2)
        ts.append(float(temperature))
        tcb.append(float(temperature))
    if not ids or len(ids)!=len(set(ids)):
        raise SPSectionInputError("unique real reinforcing bars required")
    for theta in temps:
        concrete_at_sp_fire(concrete,float(theta),normal=cb)
    free_c=np.asarray([concrete_free_thermal_strain_sp(float(T),aggregate)
        or 0. for T in temps],dtype=float)
    free_cb=np.asarray([concrete_free_thermal_strain_sp(float(T),aggregate)
        or 0. for T in tcb],dtype=float)
    free_s=np.asarray([steel_free_thermal_strain_sp(float(T)) for T in ts],dtype=float)
    bx=np.asarray(bx,dtype=float);by=np.asarray(by,dtype=float)
    b=SPPreparedSection(
        x=X.ravel(),y=Y.ravel(),u=(X.ravel()-width/2.)/(width/2.),
        v=(Y.ravel()-height/2.)/(height/2.),
        area=np.full(grid*grid,width*height/(grid*grid)),
        theta_c=temps,eps_th_c=free_c,
        bar_x=bx,bar_y=by,
        bar_u=(bx-width/2.)/(width/2.),
        bar_v=(by-height/2.)/(height/2.),
        bar_area=np.asarray(As,dtype=float),
        theta_s=np.asarray(ts),theta_cb=np.asarray(tcb),
        eps_th_s=free_s,eps_th_cb=free_cb,
        b_m=width,h_m=height,
        fck_MPa=float(cb["f_ck_MPa"]),
        fyk_MPa=float(ss["f_yk_MPa"]),
        Es_MPa=float(ss["E_s_GPa"])*1000.,
        aggregate=aggregate,production_route="SP_TABLE10",
        ductility_class="NOT_SP_QUALIFIED",high_temperature_tail="ZERO_CONCRETE_ABOVE800",
        boundary_max_C=float(field["snapshot"]["boundary_max_C"]),
        boundary_gap=False,hot_fibre_count=0,
        bar_ids=tuple(ids),
        source={
            "model":VERSION,
            "SP_fire":"СП 2.02.05-2026 §§8.2.18–8.2.20, Tables9–12, Eq6",
            "SP_normal":"СП 5.03.01-2020 §§6.1.5.4,6.2.2.13",
            "concrete_policy":"USER_ASSUME_ZERO_STRENGTH_IF_T>800_C",
            "thermal":("SP2026_8.2.23_K1_FVM_SOURCE_LAWS_WITH_UNQUALIFIED_BOUNDARY"
                if method=="SP2026_8.2.23_FVM"
                else "TKP_4.3.2_FVM_UNQUALIFIED_AS_SP_823"),
            "thermal_property_convergence_qualified":False,
            "full_member_R_t_qualified":False})
    # Explicit corners + exposed/unexposed face midpoints. Temperature is
    # sampled from SP-R2 boundary-face heat solution, never TKP guesses.
    boundary_xy_mm=[(0.,0.),(width*1000.,0.),
        (0.,height*1000.),(width*1000.,height*1000.),
        (width*500.,0.),(width*500.,height*1000.),
        (0.,height*500.),(width*1000.,height*500.)]
    b.sp_boundary_u=np.asarray([
        2.*x/(width*1000.)-1. for x,_ in boundary_xy_mm],dtype=float)
    b.sp_boundary_v=np.asarray([
        2.*y/(height*1000.)-1. for _,y in boundary_xy_mm],dtype=float)
    b.sp_boundary_temperature=np.asarray([
        temperature_at(field,x,y) for x,y in boundary_xy_mm],dtype=float)
    b.sp_boundary_free_strain=np.asarray([
        concrete_free_thermal_strain_sp(float(T),aggregate) or 0.
        for T in b.sp_boundary_temperature],dtype=float)
    b.sp_concrete=concrete
    b.sp_steel=steel
    b.sp_concrete_normal=cb
    b.sp_steel_normal=ss
    return b


def prepare_sp2026_full_nonlinear_section(column, thermal_snapshot, *, grid=12):
    """Prepare full SP5 §6.1.5.2 instantaneous rational curve separately.

    The assumed hot invariance of εc1 and εcu1 is NOT in SP2026.
    No direct normative ULS may be inferred; full curve does not
    override the existing simplified SP5 §6.1.5.4 section branch.
    """
    from rc_fire.materials.sp2026_full_nonlinear import (
        MODE, concrete_full_nonlinear_stress_sp,
        full_concrete_sp_parameters)
    prepared=prepare_sp2026_section(column,thermal_snapshot,grid=grid)
    if thermal_snapshot.get("thermal_method")!="SP2026_8.2.23_FVM":
        raise SPSectionInputError("full nonlinear SP requires independent SP heat")
    # Audit material domain before giving any law to Newton. In particular,
    # a hot beta/k combination with fixed ambient εc1 can make the SP5
    # rational denominator singular. Never 'repair' by inventing εc1(T).
    material_data=[]
    for t in set(float(x) for x in np.concatenate((
            prepared.theta_c,prepared.theta_cb,prepared.sp_boundary_temperature))):
        p=full_concrete_sp_parameters(
            t,prepared.sp_concrete,prepared.sp_concrete_normal)
        if p["fcm_theta_MPa"]>0 and p["shape_parameter_k"]<=1.:
            raise SPSectionInputError(
                "full SP5 hot constitutive mapping singular: k<=1; "
                "experimental εc1(T) needed; no interpolation or invented strain")
        material_data.append(p)
    prepared.sp_concrete_stress_fn=concrete_full_nonlinear_stress_sp
    prepared.sp_constitutive_mode=MODE
    prepared.sp_full_nonlinear_material_evidence=material_data
    prepared.source={**prepared.source,
        "SP5_full_nonlinear":"§6.1.5.2 Eq (6.13)-(6.16)",
        "temperature_peak_strain_assumption":"AMBIENT_EPS_C1_AND_CU1_UNCHANGED_NOT_NORMATIVE",
        "normative_fire_constitutive_qualified":False}
    return prepared


def evaluate_sp2026_section_at_time(column,thermal_snapshot,*,grid=12):
    """One SP heated-section equilibrium at the exact supplied time."""
    prepared=prepare_sp2026_section(column,thermal_snapshot,grid=grid)
    sections=column.get("sections") or []
    states=[]
    for s in sections:
        if not all(k in s for k in ("N_kN","Mx_kNm","My_kNm")):
            raise SPSectionInputError("fire-design actions N/Mx/My missing")
        state=prepared.solve_actions(
            s["N_kN"],s["Mx_kNm"],s["My_kNm"])
        states.append({"id":s["id"],
            "N_kN":s["N_kN"],"Mx_kNm":s["Mx_kNm"],"My_kNm":s["My_kNm"],
            "equilibrium":state})
    return {
        "version":VERSION,
        "SP_mechanical_model":"SP2026_TABLE9_10_SP5_6_1_5_4_6_2_2_13",
        "temperature_method":thermal_snapshot["thermal_method"],
        "time_minutes":float(thermal_snapshot["snapshot"]["time_minutes"]),
        "concrete_zero_strength_over_800_C_count":int(
            np.count_nonzero(prepared.theta_c>800.)),
        "concrete_zero_strength_at_bar_centres_count":int(
            np.count_nonzero(prepared.theta_cb>800.)),
        "max_steel_temperature_C":float(np.max(prepared.theta_s)),
        "max_concrete_cell_temperature_C":float(np.max(prepared.theta_c)),
        "sections":states,
        "R_t_minutes":None,
        "member_utilization_U_t":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "normative_claim":False,
        "qualification_blockers":[
            "SP_823_THERMAL_MATERIAL_AND_MESH_VALIDATION",
            "SP_819_SIGNED_THERMAL_SHRINKAGE_HISTORY_NOT_QUALIFIED",
            "SP5_TEMPERATURE_CONSTITUTIVE_CURVE_AND_BETA_ALIGNMENT",
            "FULL_COLUMN_SECOND_ORDER_EQUILIBRIUM_NOT_SOLVED",
            "ULTIMATE_CAPACITY_AND_FIRST_FAILURE_TIME_NOT_SOLVED",
            "FIRE_SPALLING_ASSESSMENT_NOT_CLOSED"],
        }
