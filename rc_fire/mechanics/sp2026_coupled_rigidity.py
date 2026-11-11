"""SP-R.7: full signed 3x3 section matrix and TWO-AXIS coupled stability.

SP5 §8.1.2.3 Eq (8.1),(8.2): N/Mx/My stiffness, including
R12/R13 axial-flexural terms and R23 bending-bending coupling.
SP5 §8.1.6.2-.5 Eq (8.54)-(8.64): NOMINAL flexural stiffness;
SP2026 §8.2.18 Tables 9/10: temperature-reduced E, strengths.

The source Eq8.2 explicitly uses *secant* material moduli at the
solved section state; the thermal Table9 beta E is DIFFERENT and is
used below for a separately named linear temperature-weighted
rigidity. The SP5 scalar nominal-k applied to a *coupled* stiffness
matrix is a transparent mathematical EXTENSION, not a provision in
SP5 for arbitrary nonuniform T(x,y). Never certify U(t) or t_R.

Coordinate convention: q=[eps0, kappa_x, kappa_y],
strain=eps0+kappa_x*(y-h/2)+kappa_y*(x-b/2);
M=[M_x,M_y] = integral sigma*[y-h/2,x-b/2]dA,
so K is symmetric and work-conjugate. In SP5's Eq8.3 sign
convention, change the signs of BOTH curvature coordinates and
conjugate bending moments consistently. This is not a sign error.
"""
from __future__ import annotations
import math
import numpy as np
from rc_fire.materials.sp2026_fire import (
    concrete_at_sp_fire,steel_at_sp_fire,SPFireMaterialError)
from rc_fire.mechanics.sp2026_nominal_member import (
    SP5NominalMemberError,nonuniform_sp5_nominal_axis)

VERSION="SP-R7-SP5-8.1.2-3x3-coupled-nominal-v1"

def _finite(value,label,*,positive=False):
    if isinstance(value,bool):
        raise SP5NominalMemberError(label+" must be finite")
    try:n=float(value)
    except (TypeError,ValueError) as exc:
        raise SP5NominalMemberError(label+" must be finite") from exc
    if not math.isfinite(n) or (positive and n<=0):
        raise SP5NominalMemberError(label+" must be positive finite")
    return n

def _moduli_inventory(prepared, *,kind,unknowns=None):
    if kind=="HOT_BETA_SOURCE_ELASTIC":
        p=prepared
        pars=getattr(p,"sp5_design_parameters",None)
        if not isinstance(pars,dict):
            raise SP5NominalMemberError("SP5 design section required")
        Ec=np.array([pars["Ecd_20_MPa"]*
            concrete_at_sp_fire(p.sp_concrete,float(t),
                p.sp_concrete_normal).modulus_factor for t in p.theta_c])
        Es=np.array([pars["Es_20_MPa"]*
            steel_at_sp_fire(p.sp_steel,float(t),
                p.sp_steel_normal).modulus_factor for t in p.theta_s])
        Eb=np.array([pars["Ecd_20_MPa"]*
            concrete_at_sp_fire(p.sp_concrete,float(t),
                p.sp_concrete_normal).modulus_factor for t in p.theta_cb])
    elif kind=="SP5_8_1_2_SOURCE_SECANT_AT_EQUILIBRIUM":
        # Exact Eq8.2 secant E'=sigma/eps for the SP5 design
        # stress-strain laws at a declared actual equilibrium state.
        if unknowns is None:
            raise SP5NominalMemberError("secant Eq8.2 requires 3 solved section unknowns")
        u=np.asarray(unknowns,dtype=float)
        if u.shape!=(3,) or not np.all(np.isfinite(u)):
            raise SP5NominalMemberError("section strain/curvatures invalid")
        if not hasattr(prepared,"sp_concrete_stress_fn"):
            raise SP5NominalMemberError("SP5 design material law missing")
        e0,gx,gy=u
        ec=e0+gx*prepared.v+gy*prepared.u+prepared.eps_th_c
        es=e0+gx*prepared.bar_v+gy*prepared.bar_u+prepared.eps_th_s
        eb=e0+gx*prepared.bar_v+gy*prepared.bar_u+prepared.eps_th_cb
        def secant(stress_fn,eps,t,mat,norm):
            out=[]
            for e,temperature in zip(eps,t):
                values=stress_fn(float(e),float(temperature),mat,norm)
                sigma,tangent=values[0],values[1]
                if not math.isfinite(float(sigma)+float(tangent)):
                    raise SP5NominalMemberError("non-finite SP5 secant")
                # At epsilon=0, use derivative limit rather than 0/0.
                k=tangent if abs(e)<1e-11 else sigma/e
                if k< -1e-7 or not math.isfinite(k):
                    raise SP5NominalMemberError("negative secant stiffness")
                out.append(max(0.,k))
            return np.asarray(out,dtype=float)
        Ec=secant(prepared.sp_concrete_stress_fn,ec,prepared.theta_c,
                   prepared.sp_concrete,prepared.sp_concrete_normal)
        Es=secant(prepared.sp_steel_stress_fn,es,prepared.theta_s,
                   prepared.sp_steel,prepared.sp_steel_normal)
        Eb=secant(prepared.sp_concrete_stress_fn,eb,prepared.theta_cb,
                   prepared.sp_concrete,prepared.sp_concrete_normal)
    else:
        raise SP5NominalMemberError("source stiffness kind unsupported")
    return Ec,Es,Eb


def _three_by_three(prepared,Ec,Es,Eb,*,concrete_bar_displacement):
    """K for [epsilon0,kappax,kappay] in kN,kNm,kNm2 units.

    For geometric condensation ALL dimensions are physical metres.
    Cell own second moment is included, not approximated by a centre
    point, so an isothermal rectangle reproduces Ic *exactly*.
    """
    A=np.asarray(prepared.area,dtype=float)
    B=np.asarray(prepared.bar_area,dtype=float)
    xc=np.asarray(prepared.x,dtype=float)-prepared.b_m/2.
    yc=np.asarray(prepared.y,dtype=float)-prepared.h_m/2.
    xs=np.asarray(prepared.bar_x,dtype=float)-prepared.b_m/2.
    ys=np.asarray(prepared.bar_y,dtype=float)-prepared.h_m/2.
    if (len(A)!=len(Ec) or len(B)!=len(Es) or len(B)!=len(Eb)):
        raise SP5NominalMemberError("thermal/material/fibre inventory mismatch")
    g=int(round(math.sqrt(len(A))))
    if g*g!=len(A):
        raise SP5NominalMemberError("SP5 mechanical section must use square fibre grid")
    dx=prepared.b_m/g;dy=prepared.h_m/g
    Qc=np.column_stack([np.ones(len(A)),yc,xc])
    Qs=np.column_stack([np.ones(len(B)),ys,xs])
    Kc=1000.*(Qc.T@(A[:,None]*Ec[:,None]*Qc))
    Kc[1,1]+=1000.*np.dot(A,Ec)*dy*dy/12.
    Kc[2,2]+=1000.*np.dot(A,Ec)*dx*dx/12.
    Ks=1000.*(Qs.T@(B[:,None]*Es[:,None]*Qs))
    Kb=1000.*(Qs.T@(B[:,None]*Eb[:,None]*Qs))
    if concrete_bar_displacement:
        # SP5 Eq8.2 uses ACTUAL material areas; the concrete under
        # steel rods must not also be counted as gross concrete.
        Kc=Kc-Kb
    for name,K in (("concrete",Kc),("steel",Ks)):
        if not np.all(np.isfinite(K)) or K[0,0]<0:
            raise SP5NominalMemberError(name+" stiffness invalid")
    return Kc,Ks,Kb


def _condense(K):
    K=np.asarray(K,dtype=float)
    if K.shape!=(3,3) or not np.all(np.isfinite(K)) or not np.allclose(
            K,K.T,rtol=1e-11,atol=1e-8):
        raise SP5NominalMemberError("section K 3x3 nonsymmetric/nonfinite")
    if K[0,0]<=0:
        raise SP5NominalMemberError("nonpositive axial rigidity")
    d=K[1:,1:]-np.outer(K[1:,0],K[0,1:])/K[0,0]
    d=(d+d.T)/2.
    if np.linalg.eigvalsh(d)[0]<=0:
        raise SP5NominalMemberError("nonpositive condensed biaxial flexural rigidity")
    return d,K[0,1:]/K[0,0]


def coupled_sp5_hot_section_stiffness(prepared,*,N_kN,length_m,
                                      effective_creep_phi,
                                      kind="HOT_BETA_SOURCE_ELASTIC",
                                      unknowns=None):
    """Build source-explicit full K, Schur-condensed D, coupled modes.

    Literal SP5 §8.1.6 k2a depends on λa in x/y. The ONLY
    symmetric positive mapping to a 3x3 bending matrix used here is
    S=diag(1,sqrt(kx),sqrt(ky)); K_nom=S K_c S+K_steel.
    This symmetric scaling is an explicit engineering HYPOTHESIS
    for nonuniform fire/cross coupling, NEVER source-certified.
    """
    N=_finite(N_kN,"N",positive=True);L=_finite(length_m,"L",positive=True)
    if isinstance(effective_creep_phi,(tuple,list)) and len(
            effective_creep_phi)==2:
        phi_axes=[_finite(x,"phi_eff axis") for x in effective_creep_phi]
    elif not isinstance(effective_creep_phi,(tuple,list,dict,np.ndarray)):
        ph=_finite(effective_creep_phi,"phi_eff")
        phi_axes=[ph,ph]
    else:
        raise SP5NominalMemberError("phi_eff requires scalar or x/y pair")
    if any(x<0 for x in phi_axes):
        raise SP5NominalMemberError("negative creep coefficient")
    params=getattr(prepared,"sp5_design_parameters",None)
    if not isinstance(params,dict):
        raise SP5NominalMemberError("SP5 source design section required")
    Ec,Es,Eb=_moduli_inventory(prepared,kind=kind,unknowns=unknowns)
    displacement=(kind=="SP5_8_1_2_SOURCE_SECANT_AT_EQUILIBRIUM")
    Kc,Ks,Kb=_three_by_three(
        prepared,Ec,Es,Eb,concrete_bar_displacement=displacement)
    K=Kc+Ks
    D,axial_offset=_condense(K)
    fcd_coeff=np.array([concrete_at_sp_fire(
        prepared.sp_concrete,float(t),prepared.sp_concrete_normal
        ).strength_factor for t in prepared.theta_c])
    fcd_eq=(np.dot(prepared.area,fcd_coeff)*
            params["fcd_20_MPa"]/(prepared.b_m*prepared.h_m))
    if fcd_eq<=0:raise SP5NominalMemberError("heated concrete design strength zero")
    Ac=prepared.b_m*prepared.h_m
    n=N/(1000.*Ac*fcd_eq)
    kc=[];lambda_a=[]
    for axis,Ic in enumerate((prepared.b_m*prepared.h_m**3/12.,
               prepared.h_m*prepared.b_m**3/12.)):
        lam=L/math.sqrt(Ic/Ac)
        k1=math.sqrt(params["f_ck_MPa"]/20.)
        k2=min(.20,n*lam/170.)
        kc.append(k1*k2/(1.+phi_axes[axis]))
        lambda_a.append(lam)
    S=np.diag([1.,math.sqrt(kc[0]),math.sqrt(kc[1])])
    K_nom=S@Kc@S+Ks
    D_nom,nom_axial_offset=_condense(K_nom)
    values,vecs=np.linalg.eigh(D_nom)
    ncrit=math.pi**2*values/L**2
    stable=bool(N<float(ncrit[0]))
    # Matrix amplification is defined only on a strictly positive
    # stable branch of the EULER-IDEALIZED nominal beam model.
    amplify=(vecs@np.diag(1./(1.-N/ncrit))@vecs.T if stable else None)
    nonsymmetric_field=bool(
        (np.ptp(prepared.theta_c)>1e-6 or
         np.ptp(prepared.theta_s)>1e-6 or
         abs(float(prepared.theta_c[0])-float(prepared.theta_s[0]))>1e-6))
    return {
        "version":VERSION,
        "source_section":"SP5 §8.1.2.3 Eqs(8.1–8.3)",
        "source_nominal":"SP5 §8.1.6 Eqs(8.54–8.64)",
        "source_temperature":"SP2026 §8.2.18 Table9 and Table10",
        "modulus_basis":kind,
        "concrete_gross_without_bar_subtraction":not displacement,
        "source_section_secant_requires_solved_state":displacement,
        "full_3x3_K":K.tolist(),
        "concrete_3x3_K":Kc.tolist(),
        "steel_3x3_K":Ks.tolist(),
        "hot_coupled_condensed_D_kNm2":D.tolist(),
        "hot_stiffness_axial_flexural_offsets_m":axial_offset.tolist(),
        "k1a":math.sqrt(params["f_ck_MPa"]/20.),
        "k2a_by_axis":[min(.20,n*lam/170.) for lam in lambda_a],
        "kc_nominal_by_axis":kc,
        "effective_creep_phi_by_axis":phi_axes,
        "hot_creep_physical_history_qualified":False,
        "fcd_equivalent_MPa":float(fcd_eq),
        "nominal_3x3_K":K_nom.tolist(),
        "nominal_2x2_D_kNm2":D_nom.tolist(),
        "nominal_axial_flexural_offsets_m":nom_axial_offset.tolist(),
        "principal_axes_unit_vectors":vecs.tolist(),
        "principal_bending_stiffness_kNm2":values.tolist(),
        "principal_Euler_Ncrit_kN":ncrit.tolist(),
        "minimum_nominal_Euler_Ncrit_kN":float(ncrit[0]),
        "N_below_first_nominal_bifurcation":stable,
        "coupled_amplification_matrix":amplify.tolist() if stable else None,
        "cross_axis_coupling_present":bool(abs(D_nom[0,1])>1e-8 or
                                            np.max(np.abs(nom_axial_offset))>1e-8),
        "spatial_heat_nonuniform":nonsymmetric_field,
        "nominal_cross_axis_scaling_is_source_defined":False,
        "SP5_8_1_6_nonuniform_fire_method_qualified":False,
        "material_history_and_thermal_curvature_qualified":False,
        "actual_first_physical_failure_qualified":False,
        "normative_claim":False}


def magnify_coupled_first_order_moments(rigidity,moments_kNm):
    """Two-axis Euler modal transformation, not scalar eta_x/eta_y."""
    m=np.asarray(moments_kNm,dtype=float)
    if m.shape!=(2,) or not np.all(np.isfinite(m)):
        raise SP5NominalMemberError("first order Mx/My required")
    a=rigidity.get("coupled_amplification_matrix")
    if a is None:
        return {"status":"FIRST_NOMINAL_EULER_MODE_CRITICAL_OR_UNKNOWN",
                "M2_kNm":None,"physical_member_failed":None,
                "normative_claim":False}
    M2=np.asarray(a,dtype=float)@m
    return {
        "status":"COUPLED_NOMINAL_MOMENTS_COMPUTED",
        "M0_kNm":m.tolist(),"M2_kNm":M2.tolist(),
        "two_axis_coupling_used":True,
        "SP5_8_1_6_nonuniform_fire_qualified":False,
        "actual_member_failed":None,
        "normative_claim":False}


def audit_independent_global_coupled_euler(rigidity,*,length_m,
                                           node_counts=(9,17),
                                           target_relative_error=.005):
    """Actual 2x2 heated nominal D embedded into independent BEAM FE.

    K and geometric G are assembled by production beam shape functions,
    while the reference is the closed-form first principal Euler load
    pi²*eig_min(D)/L². The first eigenvalue is valid regardless of
    whether the *second* bending mode aliases a higher harmonic.
    This verifies FE/global geometry, not physical heated RC collapse.
    """
    from rc_fire.member.coupled import (
        LinearSectionLaw,EndSupport,_beam_assembly,_boundary_matrix)
    L=_finite(length_m,"length_m",positive=True)
    D=np.asarray(rigidity.get("nominal_2x2_D_kNm2"),dtype=float)
    if (D.shape!=(2,2) or not np.all(np.isfinite(D)) or
        not np.allclose(D,D.T,atol=1e-9,rtol=1e-10) or
        np.linalg.eigvalsh(D)[0]<=0):
        raise SP5NominalMemberError("valid symmetric positive 2x2 rigidity required")
    target=_finite(target_relative_error,"relative tolerance",positive=True)
    if target>.1 or type(node_counts) not in (tuple,list) or (
            len(node_counts)<2 or any(type(x) is not int or x<3 or x>65
            for x in node_counts) or
            any(a>=b for a,b in zip(node_counts,node_counts[1:]))):
        raise SP5NominalMemberError("increasing 3..65 FE grid nodes required")
    exact=float(math.pi**2*np.linalg.eigvalsh(D)[0]/L**2)
    trials=[]
    for count in node_counts:
        z=np.linspace(0.,L,count)
        law=LinearSectionLaw(
            D,provenance="SP-R7 actual temperature-dependent coupled nominal D")
        zeros=np.zeros(4*count)
        _,K,G,_,_=_beam_assembly(
            z,0.,lambda i,j:law,zeros,zeros,
            np.zeros((count,2)),zeros)
        fixed,_=_boundary_matrix(
            EndSupport("pinned"),EndSupport("pinned"),count)
        free=[i for i in range(4*count) if i not in fixed]
        A=np.linalg.solve(K[np.ix_(free,free)],G[np.ix_(free,free)])
        spectrum=np.linalg.eigvals(A)
        if np.max(np.abs(spectrum.imag))>1e-7:
            raise SP5NominalMemberError("complex FE buckling eigenvalues")
        inverse_loads=[float(x) for x in spectrum.real if x>1e-13]
        if not inverse_loads:
            raise SP5NominalMemberError("FE global positive Euler mode absent")
        fe=1./max(inverse_loads)
        trials.append({
            "beam_nodes":count,"Ncrit_FE_kN":fe,
            "Ncrit_analytic_min_principal_kN":exact,
            "relative_error":abs(fe-exact)/exact,
            "within_numerical_study_tolerance":abs(fe-exact)/exact<=target})
    return {
        "version":VERSION,
        "status":("GLOBAL_COUPLED_FE_FIRST_MODE_NUMERICALLY_VERIFIED" if
                  all(x["within_numerical_study_tolerance"] for x in trials)
                  else "GLOBAL_COUPLED_FE_FIRST_MODE_NOT_CONVERGED"),
        "Ncrit_first_principal_analytic_kN":exact,
        "global_FE_grid_study":trials,
        "max_relative_error":max(x["relative_error"] for x in trials),
        "complete_hot_RC_member_first_failure_qualified":False,
        "source_nonuniform_nominal_method_qualified":False,
        "regulatory_claim":False}
