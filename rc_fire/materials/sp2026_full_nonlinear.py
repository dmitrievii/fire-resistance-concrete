"""Source-explicit SP5 §6.1.5.2 full concrete curve with SP2026 hot factors.

Physical scope: *instantaneous short-term* uniaxial compression under
declared temperature, with the SP5 peak strain and ultimate strain held
at their AMBIENT values as an exploratory convention. SP2026 §8.2.18
provides hot strength k_c and elastic beta, but does NOT explicitly
supply temperature-dependent epsilon_c1, epsilon_cu1 or transient creep.
The unvalidated strain-versus-temperature closure MUST NEVER be
promoted to a normative global R(t) by the FE solver or green CI.

This file is a separate research branch from the §6.1.5.4 simplified
section-resistance parabola. It does not overwrite the existing SP-R1
source functions. Beyond 800 °C concrete stress/modulus are zero
by the user's declared conservative rule, not by SP Table 9.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from rc_fire.materials.normative import ConcreteMix, normal_concrete
from rc_fire.materials.sp2026_fire import (
    SPFireMaterialError, concrete_at_sp_fire, steel_at_sp_fire)

VERSION="SP-R5-SP5-6.1.5.2-full-curve-hot-parameterized-v1"
SOURCE="СП 5.03.01-2020 §§6.1.5.1–6.1.5.2, eq. (6.13–6.16); СП 2.02.05-2026 §8.2.18 Table 9"
MODE="FULL_SP5_6_1_5_2_AMBIENT_PEAK_AT_HOT_T_EXPLORATORY"


def _finite(x,name):
    try:
        if isinstance(x,bool):raise TypeError
        n=float(x)
    except (ValueError,TypeError) as exc:
        raise SPFireMaterialError(name+" must be finite numeric") from exc
    if not math.isfinite(n):
        raise SPFireMaterialError(name+" must be finite numeric")
    return n


def full_concrete_sp_parameters(theta_C, concrete:ConcreteMix, normal=None):
    """Compute source equations and distinct SP Table-9 beta-modulus audit.

    SP5 §6.1.5.2 calls for Ecm,n=22*(fcm/10)^0.3 GPa, and
    k=1.1 Ecm,n * epsilon_c1 / fcm. Under heating both strength and
    modulus are reduced explicitly. Holding ambient epsilon_c1 and
    epsilon_cu1 at hot T is an independently flagged *assumption*.

    SP5 §6.1.5.1 figure supplies ultimate compression epsilon_cu1
    = min(3.5, 2.8+27*((98-fcm)/100)^4) permille.
    """
    t=_finite(theta_C,"theta")
    mat=concrete_at_sp_fire(concrete,t,normal)
    norm=normal if normal is not None else normal_concrete(concrete)
    fcm0=_finite(norm["f_cm_MPa"],"f_cm")
    e1=_finite(norm["eps_c1_permille"],"epsilon_c1")/1000.
    if not fcm0>0 or not e1>0:
        raise SPFireMaterialError("SP5 full concrete input outside valid range")
    fcm=fcm0*mat.strength_factor
    ecmn0=22000.*(fcm0/10.)**.3
    ecmn_theta=ecmn0*mat.modulus_factor
    eu=(min(3.5,2.8+27.*((98.-fcm0)/100.)**4))/1000.
    k=(1.1*ecmn_theta*e1/fcm) if fcm>0. else None
    if fcm>0. and (k is None or not math.isfinite(k) or k<=1.):
        raise SPFireMaterialError("Full SP5 law shape k<=1: no admissible source-compatible nonlinear curve")
    return {
        "source":SOURCE,"mode":MODE,
        "theta_C":t,"fcm_normal_MPa":fcm0,"fcm_theta_MPa":fcm,
        "Ecm_n_normal_MPa":ecmn0,
        "Ecm_n_hot_MPa":ecmn_theta,
        "SP_table9_beta_Ecm_normal_hot_MPa":mat.elastic_modulus_MPa,
        "SP_table9_kc":mat.strength_factor,
        "SP_table9_beta":mat.modulus_factor,
        "epsilon_c1_assumed_temperature_invariant":e1,
        "epsilon_cu1_assumed_temperature_invariant":eu,
        "shape_parameter_k":k,
        "temperature_strain_limits_qualified":False,
        "temperature_peak_strain_qualified":False,
        "creep_transient_and_unloading_qualified":False,
        "source_short_term_full_curve_applied_with_explicit_hot_assumption":True,
        "user_concrete_zero_above_800_not_normative":bool(t>800.),
        "normative_claim":False}


def concrete_full_nonlinear_stress_sp(eps_mechanical,theta_C,
                                       concrete:ConcreteMix,normal=None):
    """Return (stress MPa,tangent MPa,assumed eps_cu1, material).

    Compression positive. Implement EXACT rational shape in SP5 Eq6.13,
    with k from Eq6.15. Beyond the currently assumed epsilon_cu1
    evaluate the formal curve for *research continuation only* while
    signalling exceeding; do not hold a fictitious plastic plateau.
    At stresses beyond domain, the solver must not infer certified ULS.
    """
    eps=_finite(eps_mechanical,"strain")
    mat=concrete_at_sp_fire(concrete,theta_C,normal)
    if mat.strength_MPa==0.:
        return 0.,0.,None,mat
    if eps<=0.:
        p=full_concrete_sp_parameters(theta_C,concrete,normal)
        return 0.,0.,p["epsilon_cu1_assumed_temperature_invariant"],mat
    p=full_concrete_sp_parameters(theta_C,concrete,normal)
    e1=p["epsilon_c1_assumed_temperature_invariant"]
    eu=p["epsilon_cu1_assumed_temperature_invariant"]
    k=p["shape_parameter_k"]
    x=eps/e1
    denom=1.+(k-2.)*x
    if not math.isfinite(denom) or denom<=0.:
        raise SPFireMaterialError("SP5 full rational concrete curve has singular/nonpositive denominator")
    f=p["fcm_theta_MPa"]
    sigma=f*(k*x-x*x)/denom
    tangent=(f/e1)*(k-2.*x-(k-2.)*x*x)/(denom*denom)
    if not math.isfinite(sigma+tangent):
        raise SPFireMaterialError("SP5 full concrete nonfinite result")
    # Negative stress at extrapolated extreme strains is physically
    # impossible and cannot supply an artificial tensile branch.
    if sigma<0.:
        raise SPFireMaterialError("SP5 full concrete branch extrapolated to negative compression")
    return sigma,tangent,eu,mat


@dataclass(frozen=True)
class SP5RebarDuctility:
    """Measured/user-specific, NOT imputed from minimum A/B/C table values."""
    k_ftk_over_fyk:float
    epsilon_uk:float
    gamma_s:float
    material_certificate:str

    def validate(self):
        k=_finite(self.k_ftk_over_fyk,"k_ftk_over_fyk")
        uk=_finite(self.epsilon_uk,"epsilon_uk")
        gamma=_finite(self.gamma_s,"gamma_s")
        if k<1. or uk<=0. or gamma<=0. or not str(self.material_certificate).strip():
            raise SPFireMaterialError("actual steel k, epsilon_uk, gamma_s, certificate required")
        return self


def steel_sp5_ascending_stress(eps_mechanical,theta_C,steel, *,
                              ductility:SP5RebarDuctility,normal=None):
    """SP5 §6.2.2.13 rising bilinear branch with certified steel inputs.

    Reported epsilon_ud=0.9 epsilon_uk is a structural DESIGN limit
    under the chosen branch, not a proven high-temperature rupture law.
    The SP2026 Table10 k_s and beta scale yield and E respectively;
    temperature sensitivity of epsilon_uk is not given in Table10 and
    remains a mandatory experimental qualification gate.
    """
    d=ductility.validate()
    eps=_finite(eps_mechanical,"steel strain")
    mat=steel_at_sp_fire(steel,theta_C,normal)
    ey=mat.strength_MPa/mat.elastic_modulus_MPa
    eu=.9*d.epsilon_uk
    if eu<=ey:
        raise SPFireMaterialError("steel eps_ud <= hot yield strain; unqualified")
    abs_eps=abs(eps)
    if abs_eps<=ey:
        sigma=mat.elastic_modulus_MPa*eps
        E=mat.elastic_modulus_MPa
    else:
        # Use only the explicit declared design strength convention.
        fy=mat.strength_MPa/d.gamma_s
        fu=d.k_ftk_over_fyk*mat.strength_MPa/d.gamma_s
        eyd=fy/mat.elastic_modulus_MPa
        if eu<=eyd:
            raise SPFireMaterialError("steel epsilon_ud not beyond design yield")
        slope=(fu-fy)/(eu-eyd)
        if abs_eps<=eyd:
            sigma=mat.elastic_modulus_MPa*eps
            E=mat.elastic_modulus_MPa
        else:
            sigma=math.copysign(fy+slope*(abs_eps-eyd),eps)
            E=slope
    return sigma,E,eu,mat,{
        "SP5_steel_6_2_2_13_design_branch":True,
        "hot_ductility_temperature_qualified":False,
        "material_certificate":d.material_certificate,
        "normative_claim":False}
