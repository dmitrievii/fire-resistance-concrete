"""SP-R6: source-literal SP5 design-section + nominal-stiffness member route.

 СП 5.03.01-2020 §4.2.5.3, Table 4.6 (accidental gamma_c=1.20,
 gamma_s=1.00); §6.1.2.11 (alpha_cc, k_tc); §6.1.5.4 (Eq 6.17/18);
 §6.2.2.12/.13; §8.1.1.5 (minimum eccentricity);
 §8.1.2.1-.4 (general N/Mx/My section resistance);
 §8.1.6.1-.6 (Eq 8.53-8.64, nominal stiffness and slenderness).
 СП 2.02.05-2026 §§8.2.16-.23, Tables 9/10 (fire k_c, k_s, beta E).

There are TWO EXPLICIT scopes:
  1. ISOTHERMAL_LITERAL: Ecd, fcd, Es and fyd uniform: SP5 nominal B
     and eta follow the cited equations literally.
  2. NONUNIFORM_NUMERICAL_EXTENSION: source k, beta from the actual
     SP-R2 2D field integrated over real concrete cells/bars, resulting
     *weighted* B and fcd equivalent. The SP5 text does not prescribe
     this homogenization. It MUST NOT be silently called normative.

A solved 3x3 fibre equilibrium is not automatically a proof of true ULS:
Newton may converge to another root; endpoint search and hot thermal
history/spalling are not fully qualified. No unverified fire rating.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any
import numpy as np

from rc_fire.materials.sp2026_fire import (
    SPFireMaterialError,concrete_at_sp_fire,steel_at_sp_fire)
from rc_fire.mechanics.sp2026_section import (
    prepare_sp2026_section,SPSectionInputError)
from rc_fire.mechanics.action_capacity import WITHIN as SECTION_WITHIN, EXCEEDED as SECTION_EXCEEDED, UNKNOWN as SECTION_UNKNOWN

VERSION="SP-R6-SP5-section-and-nominal-member-v1"
SOURCE_SP5="СП 5.03.01-2020 §§4.2.5.3,6.1.2.11,6.1.5.4,8.1.1.5,8.1.2,8.1.6"
SOURCE_SP2026="СП 2.02.05-2026 §§8.2.16–8.2.23, Tables 9–10"
WITHIN="EQUILIBRATED_WITHIN_SECTION_CHECK_STRAINS"
EXCEEDED="EQUILIBRATED_SECTION_CHECK_LIMIT_EXCEEDED"
UNKNOWN="UNRESOLVED_SECTION_OR_MEMBER_CHECK"


class SP5NominalMemberError(ValueError):
    pass


def _finite(value,name,*,positive=False):
    if isinstance(value,bool):
        raise SP5NominalMemberError(name+": finite number required")
    try: number=float(value)
    except (TypeError,ValueError) as exc:
        raise SP5NominalMemberError(name+": finite number required") from exc
    if not math.isfinite(number) or (positive and number<=0.):
        raise SP5NominalMemberError(name+": finite "+(
            "positive" if positive else "numeric")+" value required")
    return number


@dataclass(frozen=True)
class SP5FireDesignFactors:
    # Special/accidental design situation, not automatically a validation
    # of the user's chosen fire action combination.
    gamma_c:float=1.2
    gamma_s:float=1.
    k_tc:float=1.
    design_situation:str="SP5_TABLE_4_6_ACCIDENTAL"

    def checked(self):
        if self.design_situation!="SP5_TABLE_4_6_ACCIDENTAL":
            raise SP5NominalMemberError("SP5 Table4.6 fire/accidental factors only")
        if abs(_finite(self.gamma_c,"gamma_c",positive=True)-1.2)>1e-12:
            raise SP5NominalMemberError("SP5 Table4.6 accidental gamma_c=1.2")
        if abs(_finite(self.gamma_s,"gamma_s",positive=True)-1.)>1e-12:
            raise SP5NominalMemberError("SP5 Table4.6 accidental gamma_s=1.0")
        if abs(_finite(self.k_tc,"k_tc",positive=True)-1.)>1e-12:
            raise SP5NominalMemberError("SP5 §6.1.2.11 recommended k_tc=1")
        return self


def design_parameters(normal_concrete,normal_steel,factors=None):
    """SP5 §6.1.2.11 fcd, §6.2.2.12 fyd (not fck/fyk directly)."""
    factors=(factors or SP5FireDesignFactors()).checked()
    fck=_finite(normal_concrete["f_ck_MPa"],"fck",positive=True)
    fyk=_finite(normal_steel["f_yk_MPa"],"fyk",positive=True)
    ecm=_finite(normal_concrete["E_cm_GPa"],"Ecm",positive=True)*1000.
    es=_finite(normal_steel["E_s_GPa"],"Es",positive=True)*1000.
    alpha_cc=min(1.,(40./fck)**(1./3.))
    fcd=alpha_cc*factors.k_tc*fck/factors.gamma_c
    fyd=fyk/factors.gamma_s
    return {
        "source":"SP5 §6.1.2.11 Eq6.4/6.5; §6.2.2.12 Eq6.28; Table4.6",
        "f_ck_MPa":fck,"f_yk_MPa":fyk,
        "alpha_cc":alpha_cc,"k_tc":factors.k_tc,
        "gamma_c":factors.gamma_c,"gamma_s":factors.gamma_s,
        "fcd_20_MPa":fcd,"fyd_20_MPa":fyd,
        "Ecd_20_MPa":ecm/1.2,
        "Es_20_MPa":es,
        "design_combination_is_user_declared":True}


def prepare_sp2026_design_section(column,snapshot,*,grid=12):
    """Return separate SP5 design section strength, not SP-R1 fck-only law."""
    prepared=prepare_sp2026_section(column,snapshot,grid=grid)
    if snapshot.get("thermal_method")!="SP2026_8.2.23_FVM":
        raise SP5NominalMemberError("SP5 fire design section requires SP-R2 heat")
    params=design_parameters(prepared.sp_concrete_normal,prepared.sp_steel_normal)
    def concrete_law(eps,temperature,concrete,normal):
        mat=concrete_at_sp_fire(concrete,temperature,normal)
        if mat.strength_MPa==0.:
            return 0.,0.,None,mat
        e=float(eps)
        epsilon2=_finite(normal["eps_c2_permille"],"eps_c2",positive=True)/1000.
        epsu=_finite(normal["eps_cu2_permille"],"eps_cu2",positive=True)/1000.
        exponent=_finite(normal["n_parabola"],"n",positive=True)
        fc=params["fcd_20_MPa"]*mat.strength_factor
        if e<=0.:return 0.,0.,epsu,mat
        if e>=epsilon2:return fc,0.,epsu,mat
        r=e/epsilon2
        return (fc*(1.-(1.-r)**exponent),
            fc*exponent/epsilon2*(1.-r)**(exponent-1.),epsu,mat)
    def steel_law(eps,temperature,steel,normal):
        mat=steel_at_sp_fire(steel,temperature,normal)
        fy=params["fyd_20_MPa"]*mat.strength_factor
        E=mat.elastic_modulus_MPa
        trial=float(eps)*E
        if abs(trial)>=fy:
            return math.copysign(fy,trial),0.,mat
        return trial,E,mat
    prepared.sp_concrete_stress_fn=concrete_law
    prepared.sp_steel_stress_fn=steel_law
    prepared.sp_constitutive_mode="SP5_6_1_5_4_DESIGN_SECTION_AT_FIRE"
    prepared.sp5_design_parameters=params
    prepared.source={**prepared.source,
        "design_strain_law":"SP5 §6.1.5.4 Eq6.17,6.18",
        "fire_design_strength":"SP5 Eq6.4/6.28 and Table4.6 times SP2026 Tables9/10",
        "nominal_member_stiffness":"SP5 §8.1.6",
        "nonuniform_fire_material_qualification":False}
    return prepared


def exact_sp5_nominal_axis(*,N_kN, fck_MPa, fcd_MPa,
                           Ecd_MPa, Es_MPa, Ic_m4, Is_m4,
                           Ac_m2, length_m, mu=1.,
                           effective_creep_phi):
    """Literal SP5 §8.1.6.2-.6 Eq 8.54–8.64 one-axis values.

    Ecd, Es, Ic, Is must describe a UNIFORM property section.
    A hypothetical phi_eff must be explicitly supplied and sourced
    by the caller (SP5 §8.1.6.5); no silent fire creep assumption.
    """
    N=_finite(N_kN,"N",positive=True)
    fck=_finite(fck_MPa,"fck",positive=True)
    fcd=_finite(fcd_MPa,"fcd",positive=True)
    Ec=_finite(Ecd_MPa,"Ecd",positive=True)
    Es=_finite(Es_MPa,"Es",positive=True)
    Ic=_finite(Ic_m4,"Ic",positive=True)
    Is=_finite(Is_m4,"Is")
    Ac=_finite(Ac_m2,"Ac",positive=True)
    L=_finite(length_m,"length",positive=True)
    mu=_finite(mu,"effective length factor",positive=True)
    phi=_finite(effective_creep_phi,"effective creep coefficient")
    if phi<0. or Is<0.:
        raise SP5NominalMemberError("negative creep or reinforcement inertia")
    l0=mu*L
    radius=math.sqrt(Ic/Ac)
    lam=l0/radius
    n=N/(1000.*Ac*fcd)
    k1=math.sqrt(fck/20.)
    k2=min(.20,n*lam/170.)
    kc=k1*k2/(1.+phi)
    B_concrete=kc*1000.*Ec*Ic
    B_steel=1000.*Es*Is
    Bnom=B_concrete+B_steel
    if Bnom<=0.:
        raise SP5NominalMemberError("nonpositive SP5 nominal stiffness")
    Ncrit=math.pi**2*Bnom/l0**2
    admissible=N<Ncrit
    return {
        "source":"SP5 §8.1.6.2–8.1.6.6 Eq8.54–8.64",
        "scope":"ISOTHERMAL_LITERAL_UNIFORM_SECTION",
        "N_kN":N,"Ncr_kN":Ncrit,"Bnom_kNm2":Bnom,
        "B_concrete_kNm2":B_concrete,"B_steel_kNm2":B_steel,
        "l0_m":l0,"mu":mu,"lambda_a":lam,"n":n,
        "k1a":k1,"k2a":k2,"kc_nominal":kc,
        "phi_eff":phi,"eta_a":1./(1.-N/Ncrit) if admissible else None,
        "N_below_nominal_critical":admissible,
        "when_N_at_or_above_Ncr":"OUTSIDE_NOMINAL_AMPLIFICATION_DOMAIN",
        "scope_qualified_nonuniform_fire":False,
        "normative_claim":False}


def _uniform_property(array,atol=1.e-8):
    v=np.asarray(array,dtype=float)
    return bool(np.max(v)-np.min(v)<=atol)


def nonuniform_sp5_nominal_axis(prepared,*,N_kN,length_m,
                                mu_x=1.,mu_y=1.,
                                effective_creep_phi):
    """Temperature-cell quadrature extension of §8.1.6.3 (not in text).

    Concrete beta E and hot design fcd integrated over SP-R2 2D
    *cell-centre* temperatures; exact cell own second moments included.
    Steel is point bars at SP sampled bar temperatures. Design-normal
    N and SP5 effective creep are applied consistently per axis.

    Source convention: k1a remains ambient fck class, n is computed
    from area-average hot design fcd. This **homogenization** is an
    engineering extension, not literal SP5 Eq8.61 for nonuniform fields.
    """
    params=getattr(prepared,"sp5_design_parameters",None)
    if not isinstance(params,dict):
        raise SP5NominalMemberError("design section with SP5 gamma factors required")
    N=_finite(N_kN,"N",positive=True)
    L=_finite(length_m,"length",positive=True)
    phi=_finite(effective_creep_phi,"effective creep")
    if phi<0.:
        raise SP5NominalMemberError("negative phi_eff")
    b=float(prepared.b_m);h=float(prepared.h_m)
    area=np.asarray(prepared.area,dtype=float)
    bars=np.asarray(prepared.bar_area,dtype=float)
    tc=np.asarray(prepared.theta_c,dtype=float)
    ts=np.asarray(prepared.theta_s,dtype=float)
    if len(area)!=len(tc) or len(bars)!=len(ts):
        raise SP5NominalMemberError("SP heat and actual geometry mismatch")
    mat_c=[concrete_at_sp_fire(
        prepared.sp_concrete,float(t),prepared.sp_concrete_normal) for t in tc]
    mat_s=[steel_at_sp_fire(
        prepared.sp_steel,float(t),prepared.sp_steel_normal) for t in ts]
    betac=np.array([m.modulus_factor for m in mat_c],dtype=float)
    kc_strength=np.array([m.strength_factor for m in mat_c],dtype=float)
    betas=np.array([m.modulus_factor for m in mat_s],dtype=float)
    fcd_eq=float(np.dot(area,kc_strength))*params["fcd_20_MPa"]/(b*h)
    if fcd_eq<=0.:
        return {"status":"OUTSIDE_SOURCE_STRENGTH_DOMAIN",
                "reason":"no heated concrete design compression left",
                "normative_claim":False}
    Ecd=params["Ecd_20_MPa"]*betac
    Es=params["Es_20_MPa"]*betas
    grid=int(round(math.sqrt(len(area))))
    if grid*grid!=len(area):
        raise SP5NominalMemberError("square 2D mechanical fibre grid required")
    cell_width=b/grid;cell_height=h/grid
    iy=(np.asarray(prepared.y)-h/2.)**2+cell_height**2/12.
    ix=(np.asarray(prepared.x)-b/2.)**2+cell_width**2/12.
    by=(np.asarray(prepared.bar_y)-h/2.)**2
    bx=(np.asarray(prepared.bar_x)-b/2.)**2
    Ic_x=b*h**3/12.
    Ic_y=h*b**3/12.
    ac=b*h
    # SP5 nominal B of each independent bending axis cannot be applied
    # independently to a general unsymmetrically heated section with a
    # nonzero material-weighted bending cross-term or axial-bending coupling.
    # Source-matched 2D heat does NOT justify silently dropping Dxy.
    cx=np.asarray(prepared.x,dtype=float)-b/2.
    cy=np.asarray(prepared.y,dtype=float)-h/2.
    sx=np.asarray(prepared.bar_x,dtype=float)-b/2.
    sy=np.asarray(prepared.bar_y,dtype=float)-h/2.
    weighted=np.sum(Ecd*area)+np.sum(Es*bars)
    if weighted<=0:
        raise SP5NominalMemberError("heated source section has no positive elastic material")
    xstiff=(np.dot(Ecd*area,cx)+np.dot(Es*bars,sx))/weighted
    ystiff=(np.dot(Ecd*area,cy)+np.dot(Es*bars,sy))/weighted
    EIx=1000.*(np.dot(Ecd*area,iy)+np.dot(Es*bars,by))
    EIy=1000.*(np.dot(Ecd*area,ix)+np.dot(Es*bars,bx))
    EIxy=1000.*(np.dot(Ecd*area,cx*cy)+np.dot(Es*bars,sx*sy))
    coupling=abs(EIxy)/math.sqrt(EIx*EIy) if EIx>0 and EIy>0 else math.inf
    axial_bending=max(abs(xstiff)/b,abs(ystiff)/h)
    # This is a STRICT mathematical decoupling preflight; tolerance is
    # numerical 1e-6, not a normative allowable asymmetry.
    decoupled=bool(coupling<=1e-6 and axial_bending<=1e-6)
    output={"source":"SP5 Eq8.54–8.64 + SP2026 Tables9/10",
        "scope":("ISOTHERMAL_NUMERIC_QUADRATURE" if
             _uniform_property(tc) and _uniform_property(ts)
             and abs(float(tc[0])-float(ts[0]))<1e-8
             else "NONUNIFORM_NUMERICAL_EXTENSION_NOT_PRESCRIBED"),
        "gamma_c":params["gamma_c"],"gamma_s":params["gamma_s"],
        "alpha_cc":params["alpha_cc"],
        "fcd_design_equivalent_MPa":fcd_eq,
        "phi_eff":phi,
        "EIxy_hot_before_nominal_kc_kNm2":EIxy,
        "relative_bending_cross_stiffness":coupling,
        "relative_axial_bending_stiffness_offset":axial_bending,
        "axis_decoupling_verified_numerically":decoupled,
        "axis_decoupling_tolerance_research_only":1e-6,
        "mechanical_concrete_cell_count":len(area),
        "real_steel_bar_count":len(bars),
        "interpolation_is_a_numerical_assumption":True,
        "normative_nonuniform_member_method_qualified":False,
        "normative_claim":False}
    if not decoupled:
        output["x"]={"status":"AXIS_COUPLING_UNRESOLVED",
                      "Ncrit_kN":None,"eta_a":None}
        output["y"]={"status":"AXIS_COUPLING_UNRESOLVED",
                      "Ncrit_kN":None,"eta_a":None}
        output["qualification_blocker"]=(
            "SP5 scalar nominal ηa cannot ignore nonzero EIxy or "
            "temperature-weighted eccentric stiffness centroid")
        return output
    for axis,centres,steel_pos,Ic,mu in (
            ("x",iy,by,Ic_x,mu_x),("y",ix,bx,Ic_y,mu_y)):
        l0=_finite(mu,"mu_"+axis,positive=True)*L
        n=N/(1000.*ac*fcd_eq)
        lam=l0/math.sqrt(Ic/ac)
        k1=math.sqrt(params["f_ck_MPa"]/20.)
        k2=min(.2,n*lam/170.)
        k_nom=k1*k2/(1.+phi)
        EIc=1000.*float(np.dot(area*Ecd,centres))
        EIs=1000.*float(np.dot(bars*Es,steel_pos))
        B=k_nom*EIc+EIs
        if not math.isfinite(B) or B<=0.:
            output[axis]={"status":"OUTSIDE_NOMINAL_RIGIDITY_DOMAIN",
                          "Ncrit_kN":None,"eta_a":None}
            continue
        ncr=math.pi**2*B/l0**2
        output[axis]={
            "status":("NOMINAL_AMPLIFICATION_DEFINED" if N<ncr
                     else "N_AT_OR_ABOVE_NCR"),
            "EI_concrete_hot_before_kc_kNm2":EIc,
            "EI_steel_hot_kNm2":EIs,
            "kc_nominal":k_nom,"k1a":k1,"k2a":k2,
            "n":n,"lambda_a":lam,
            "l0_m":l0,"Bnom_kNm2":B,
            "Ncrit_kN":ncr,
            "eta_a":1./(1.-N/ncr) if N<ncr else None}
    return output


def assess_sp5_nominal_column_at_fire(column,snapshot,member_spec, *,
                                      grid=12,effective_creep_phi=0.,
                                      minimum_eccentricity_enforced=True):
    """Run a section-check + nominal EI amplification, no fake R rating.

    Scope pinned/pinned actual uniform q, user-provided half-sine
    imperfection and confirmed uniform heating along length. Section
    at midspan is the critical magnitude for this q schematic only.
    This solver NEVER adds the same P–Delta moments from SP-R3 FE:
    amplification is a distinct source SP5 nominal-stiffness pathway.
    """
    if (not isinstance(member_spec,dict) or
            member_spec.get("load_mode")!="explicit_sp2026_beam" or
            member_spec.get("longitudinal_thermal_mode")!="explicit_uniform_full_length" or
            member_spec.get("uniform_exposure_confirmed") is not True or
            member_spec.get("entered_section_moments_reconciled") is not True):
        raise SP5NominalMemberError("restricted pin-pin, uniform q full member contract required")
    ends=(member_spec.get("left_support"),member_spec.get("right_support"))
    if not all(isinstance(s,dict) and s.get("x")=="pinned" and s.get("y")=="pinned"
               for s in ends):
        raise SP5NominalMemberError("first public nominal method pin-pin only")
    z=member_spec.get("z_m")
    L=_finite(column["length_m"],"length",positive=True)
    if (not isinstance(z,(list,tuple)) or len(z)!=3 or
            any(abs(float(a)-b)>1e-8 for a,b in zip(z,(0.,L/2.,L)))):
        raise SP5NominalMemberError("pin-pin q requires 0,midspan,L stations")
    N=_finite(member_spec.get("N_kN"),"N",positive=True)
    q=np.asarray(member_spec.get("distributed_load_kNpm"),dtype=float)
    imper=np.asarray(member_spec.get("initial_imperfection"),dtype=float)
    nodal=np.asarray(member_spec.get("nodal_forces"),dtype=float)
    if q.shape!=(3,2) or not np.all(np.isfinite(q)) or not np.allclose(q,q[0]):
        raise SP5NominalMemberError("constant q_x/q_y required")
    if imper.shape!=(12,) or not np.all(np.isfinite(imper)):
        raise SP5NominalMemberError("two-axis initial bow explicitly required")
    if nodal.shape!=(12,) or not np.all(np.isfinite(nodal)) or np.max(abs(nodal))>1e-8:
        raise SP5NominalMemberError("nodal forces/end moments unsupported in restricted branch")
    if type(minimum_eccentricity_enforced) is not bool or not minimum_eccentricity_enforced:
        raise SP5NominalMemberError("SP5 §8.1.1.5 e_min must be enforced")
    prep=prepare_sp2026_design_section(column,snapshot,grid=grid)
    nominal=nonuniform_sp5_nominal_axis(
        prep,N_kN=N,length_m=L,mu_x=1.,mu_y=1.,
        effective_creep_phi=effective_creep_phi)
    if "x" not in nominal or "y" not in nominal:
        status=UNKNOWN
        root=None
    elif nominal["x"]["eta_a"] is None or nominal["y"]["eta_a"] is None:
        status="N_AT_OR_ABOVE_NOMINAL_NCR_UNRESOLVED_MEMBER_CAPACITY"
        root=None
    else:
        ex=float(imper[2]);ey=float(imper[8])
        if abs(ex)>L/10 or abs(ey)>L/10:
            raise SP5NominalMemberError("out-of-domain initial imperfection")
        mx0=float(q[0,0])*L*L/8.+N*ex
        my0=float(q[0,1])*L*L/8.+N*ey
        ex_min=max(float(column["h_mm"])/30.,20.)/1000.
        ey_min=max(float(column["b_mm"])/30.,20.)/1000.
        mx0=math.copysign(max(abs(mx0),N*ex_min),mx0 if mx0 else 1.)
        my0=math.copysign(max(abs(my0),N*ey_min),my0 if my0 else 1.)
        mx2=mx0*nominal["x"]["eta_a"]
        my2=my0*nominal["y"]["eta_a"]
        root=prep.solve_actions(N,mx2,my2)
        if root.get("classification")==SECTION_WITHIN:
            status=WITHIN
        elif root.get("classification")==SECTION_EXCEEDED:
            status=EXCEEDED
        else:
            status=UNKNOWN
    return {
        "version":VERSION,"time_minutes":float(snapshot["snapshot"]["time_minutes"]),
        "status":status,"section":root,
        "nominal_second_order":nominal,
        "design_material_parameters":prep.sp5_design_parameters,
        "minimum_eccentricity_mm":{
            "x":max(column["h_mm"]/30.,20.),
            "y":max(column["b_mm"]/30.,20.)},
        "first_order_moment_reconciliation":(
            {"M0x_kNm":mx0,"M0y_kNm":my0,
             "M2x_kNm":mx2,"M2y_kNm":my2}
            if root is not None else None),
        "thermal_field_nonuniform_member_homogenization_qualified":False,
        "nominal_creep_provenance":"EXPLICIT_ANALYSIS_ASSUMPTION_NOT_AUTOMATIC_SP_CREEP",
        "material_temperature_ultimate_strain_qualified":False,
        "actual_member_capacity_U_t":None,
        "actual_t_R_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "normative_claim":False,
        "remaining_blockers":[
            "SP5_8_1_6_NONUNIFORM_FIRE_EI_AND_FCD_HOMOGENIZATION_NOT_SOURCE_PRESCRIBED",
            "SP5_8_1_6_EFFECTIVE_CREEP_FROM_8_64_NOT_PROJECT_VERIFIED",
            "SP5_8_1_1_5_ECCENTRICITY_AND_IMPERFECTION_ACTION_RECONCILIATION",
            "SP2026_8_2_23_THERMAL_SPALLING_AND_VALIDATION",
            "SP5_8_1_2_SECTION_LIMIT_FIRST_FAILURE_AND_LONGITUDINAL_VALIDATION"] }


def scan_sp5_nominal_member_history(column,heat,member_spec,times_minutes,
                                   *,grid=12,effective_creep_phi):
    """Repeated design section + nominal-B at exact stored SP-R2 time samples.

    Does not interpolate between stored thermal times and cannot declare
    a first fire failure from interval sampling, unresolved equilibria,
    or nonuniform homogenization lacking normative qualification.
    """
    from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
    if heat.get("thermal_method")!="SP2026_8.2.23_FVM":
        raise SP5NominalMemberError("source-matched SP thermal history required")
    if not isinstance(times_minutes,(list,tuple)) or not 1<=len(times_minutes)<=12:
        raise SP5NominalMemberError("1..12 exact SP-R2 stored times required")
    times=[_finite(t,"time",positive=True) for t in times_minutes]
    if any(b<=a for a,b in zip(times,times[1:])):
        raise SP5NominalMemberError("requested SP-R2 times must strictly increase")
    rows=[]
    for t in times:
        record=assess_sp5_nominal_column_at_fire(
            column,select_sp2026_snapshot(heat,t),member_spec,grid=grid,
            effective_creep_phi=effective_creep_phi)
        nominal=record["nominal_second_order"]
        rows.append({
            "time_minutes":t,
            "status":record["status"],
            "x_nominal":nominal.get("x"),
            "y_nominal":nominal.get("y"),
            "M_first_and_second":record["first_order_moment_reconciliation"],
            "section":record["section"],
            "nonuniform_method_qualified":False,
            "normative_claim":False})
    transitions=[]
    for earlier,later in zip(rows,rows[1:]):
        if earlier["status"]==WITHIN and later["status"]==EXCEEDED:
            transitions.append({
                "last_sampled_admissible_minute":earlier["time_minutes"],
                "first_sampled_exceedance_minute":later["time_minutes"],
                "physical_first_failure_proved":False})
    return {
        "version":VERSION,
        "source":"SP5 §6.1.5.4 + §8.1.6, SP2026 §8.2.18 actual heat",
        "status":"RESEARCH_NOMINAL_HISTORY_SOURCE_NONUNIFORM_NOT_CERTIFIED",
        "samples":rows,"observed_strain_check_transitions":transitions,
        "temperature_interpolation_used":False,
        "actual_U_t":None,"actual_t_R":None,
        "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}
