"""SP-R.1: strength, stiffness and thermal-strain laws from Belarus SP 2026.

Selected method: SP 2.02.05-2026 §§8.2.18–8.2.20, Tables 9–12,
formula (6), and SP 5.03.01-2020 §§6.1.5.4,6.2.2.13.
This module has NO Eurocode strength factors.

USER-DEFINED OUT-OF-TABLE CONVENTION (not in SP Table 9):
if concrete theta > 800 C, concrete has exactly ZERO compressive and
tensile resistance and ZERO tangent/elastic modulus. Do not confuse
this with SP's tabulated k_c(800)=0.10. The transition 800+ is a
deliberate discontinuity. This is an explicit conservative model
choice requiring engineering qualification, NOT source text and NOT
automatic certification of R(t).

Steel beyond 800 C remains UNRESOLVED: the user adopted zero-tail only
for concrete. We must not invent steel coefficients.

Between tabulated temperatures linear interpolation and the normal
20..200 C steel bridge are explicit numerical assumptions, not
additional tabular standard provisions.

Temperature-dependent modulus beta*Ecm and SP5 parabolic-linear fibre
compression tangent are BOTH retained as distinct source quantities;
their equality is not assumed. Member stiffness calibration is pending.

Thermal strain: integrate signed alpha_bt + alpha_cs versus theta;
the physical interpretation of alpha_cs and transient thermal
shrinkage history remains a validation gate. It is never presented
as source-qualified irreversible shrinkage in a complete fire history.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from rc_fire.materials.normative import (
    ConcreteMix, Reinforcement, MaterialError, normal_concrete,
    normal_reinforcement, concrete_at_temperature,
    reinforcement_at_temperature, concrete_thermal_strain_coefficients,
    steel_thermal_expansion)

VERSION="SP-R1-2026-materials-explicit-concrete-zero-tail-v1"
SOURCE="СП 2.02.05-2026 §§8.2.18-8.2.20, таблицы 9-12, формула (6); СП 5.03.01-2020 §§6.1.5.4,6.2.2.13"
ZERO_POLICY="USER_ASSUMPTION_CONCRETE_STRENGTH_AND_MODULUS_ZERO_ABOVE_800_C"
T_LIMIT=800.
ALPHA_KNOTS=(20.,50.,100.,300.,500.,700.,1100.)


class SPFireMaterialError(ValueError):
    pass


def _number(value,name):
    if isinstance(value,bool):
        raise SPFireMaterialError(name+": finite number required")
    try:
        result=float(value)
    except (TypeError,ValueError) as exc:
        raise SPFireMaterialError(name+": finite number required") from exc
    if not math.isfinite(result):
        raise SPFireMaterialError(name+": finite number required")
    return result


@dataclass(frozen=True)
class SPFireMaterial:
    kind:str
    temperature_C:float
    strength_factor:float
    modulus_factor:float
    strength_MPa:float
    elastic_modulus_MPa:float
    status:str
    strength_source:str
    modulus_source:str
    policy:str|None=None


def concrete_at_sp_fire(concrete:ConcreteMix,theta_C,normal=None):
    """Return SP Table9 coefficients OR requested zero concrete tail."""
    t=_number(theta_C,"concrete temperature")
    if t<20.:
        raise SPFireMaterialError("concrete temperature below 20 °C")
    norm=normal if normal is not None else normal_concrete(concrete)
    f=_number(norm["f_ck_MPa"],"normal f_ck")
    E=norm.get("E_cm_GPa")
    if E is None:
        raise SPFireMaterialError("SP 5.03.01-2020 ambient concrete Ecm unresolved")
    E=_number(E,"normal Ecm")*1000.
    if t>T_LIMIT:
        return SPFireMaterial(
            "concrete",t,0.,0.,0.,0.,"ZERO_ABOVE_SP_TABLE9",
            "USER ENGINEERING ASSUMPTION: theta>800 °C; SP table 9 stops at 800",
            "USER ENGINEERING ASSUMPTION: zero stiffness follows zero strength",
            ZERO_POLICY)
    try:
        data=concrete_at_temperature(concrete,t,normal=norm)
    except MaterialError as exc:
        raise SPFireMaterialError(str(exc)) from exc
    if data["beta_E"] is None:
        raise SPFireMaterialError(
            "SP Table9 beta unavailable for this high-strength concrete: "
            "compatible fibre stiffness is not determined")
    return SPFireMaterial(
        "concrete",t,float(data["k_c"]),float(data["beta_E"]),
        float(data["f_ck_theta_MPa"]),float(data["E_cm_theta_GPa"])*1000.,
        data["mode"],data["source"],data["source"])


def steel_at_sp_fire(steel:Reinforcement,theta_C,normal=None):
    """Use SP Table10, with explicit code-unsupported >800 range."""
    t=_number(theta_C,"steel temperature")
    if t<20. or t>800.:
        raise SPFireMaterialError(
            "SP Table 10 steel temperature outside supported 20–800 °C; "
            "concrete-zero assumption does NOT extend to steel")
    norm=normal if normal is not None else normal_reinforcement(steel)
    try:
        data=reinforcement_at_temperature(steel,t,normal=norm)
    except MaterialError as exc:
        raise SPFireMaterialError(str(exc)) from exc
    if data["f_yk_theta_MPa"] is None:
        raise SPFireMaterialError("SP5 normal steel yield resistance unavailable")
    return SPFireMaterial(
        "steel",t,float(data["k_s"]),float(data["beta_E"]),
        float(data["f_yk_theta_MPa"]),float(data["E_s_theta_GPa"])*1000.,
        data["mode"],data["source"],data["source"])


def concrete_stress_sp(eps_mechanical,theta_C,concrete:ConcreteMix,normal=None):
    """SP5 §6.1.5.4 parabolic-linear compression, positive compression.

    Returns (stress [MPa], tangent [MPa], ultimate strain, material).
    A strain exceeding eps_cu2 is signalled for ULS, but the stress
    plateau is *not* treated as proof of residual stability.
    """
    eps=_number(eps_mechanical,"concrete mechanical strain")
    mat=concrete_at_sp_fire(concrete,theta_C,normal)
    if mat.strength_MPa==0.:
        # No artificial crush failure or thermal-eigenstrain requirement
        # for a completely stress-inactive >800 C concrete fibre.
        return 0.,0.,None,mat
    norm=normal if normal is not None else normal_concrete(concrete)
    eps2=_number(norm["eps_c2_permille"],"eps_c2")/1000.
    epsu=_number(norm["eps_cu2_permille"],"eps_cu2")/1000.
    exponent=_number(norm["n_parabola"],"n parabola")
    if not 0<eps2<=epsu or exponent<=1.:
        raise SPFireMaterialError("SP5 concrete compression strain parameters invalid")
    if eps<=0.:
        return 0.,0.,epsu,mat
    if eps>=eps2:
        return mat.strength_MPa,0.,epsu,mat
    ratio=eps/eps2
    stress=mat.strength_MPa*(1.-(1.-ratio)**exponent)
    tangent=mat.strength_MPa*exponent/eps2*(1.-ratio)**(exponent-1.)
    return stress,tangent,epsu,mat


def steel_stress_sp(eps_mechanical,theta_C,steel:Reinforcement,normal=None):
    """SP5 §6.2.2.13 symmetric bilinear with horizontal upper branch.

    The chosen no-ultimate-strain branch is expressly permitted by SP5,
    but a full member first-failure condition must still be verified.
    """
    eps=_number(eps_mechanical,"steel mechanical strain")
    mat=steel_at_sp_fire(steel,theta_C,normal)
    trial=mat.elastic_modulus_MPa*eps
    if abs(trial)>=mat.strength_MPa:
        return math.copysign(mat.strength_MPa,eps),0.,mat
    return trial,mat.elastic_modulus_MPa,mat


def _integrate_piecewise(func,temperature,max_supported):
    t=_number(temperature,"thermal strain temperature")
    if not 20.<=t<=max_supported:
        raise SPFireMaterialError("thermal-strain function outside source range")
    if t==20.:
        return 0.
    cuts=[20.]+[x for x in ALPHA_KNOTS if 20.<x<t]+[t]
    value=0.
    for a,b in zip(cuts,cuts[1:]):
        value+=.5*(func(a)+func(b))*(b-a)
    return float(value)


def steel_free_thermal_strain_sp(theta_C):
    """Exact integral of SP §8.2.19 Eq. 6, relative to 20 C."""
    t=_number(theta_C,"steel temperature")
    if not 20.<=t<=800.:
        raise SPFireMaterialError("steel expansion Eq. 6 limited to 20–800 °C")
    # integral (0.005*theta+11.5)*1e-6 dtheta from 20 to t
    return (11.5*(t-20.)+.0025*(t*t-400.))*1e-6


def concrete_free_thermal_strain_sp(theta_C,family,*,signed_shrinkage=True):
    """Numerical integral of SP Tables 11-12 signed expansion/shrinkage.

    Source tables list *coefficients*, not a unique irreversible history
    integration rule. This is explicitly an unvalidated modelling
    convention; no normative member R(t) follows from it.
    For theta>800 the fibre has zero stress, so thermal strain has
    no role in stress equilibrium: report None, do not extrapolate.
    """
    t=_number(theta_C,"concrete temperature")
    if t>800.:
        return None
    if t<20.:
        raise SPFireMaterialError("concrete thermal strain below 20 °C")
    def coefficient(x):
        try: data=concrete_thermal_strain_coefficients(family,x)
        except MaterialError as exc:
            raise SPFireMaterialError(str(exc)) from exc
        return data["alpha_bt_per_C"]+(
            data["alpha_cs_per_C"] if signed_shrinkage else 0.)
    return _integrate_piecewise(coefficient,t,1100.)


def qualification_status():
    return {
        "source":SOURCE,"version":VERSION,
        "concrete_zero_tail_policy":ZERO_POLICY,
        "concrete_strength_at_800_is_not_zero":True,
        "sp_table9_above_800_is_assumption_not_normative":True,
        "steel_above_800":"BLOCKED_NO_USER_ZERO_ASSUMPTION",
        "modulus_and_sp5_parabola_tangent_are_distinct":True,
        "irreversible_thermal_shrinkage_history_qualified":False,
        "thermal_transport_qualified_sp2026":False,
        "full_member_capacity_U_t_qualified":False,
        "first_failure_t_R_qualified":False,
        "normative_claim":False,
    }
