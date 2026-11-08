"""TKP EN 1992-1-2-2009 (Belarus) material constitutive source implementation.

Normative basis: EN 1992-1-2:2004, Belarusian IDT TKP EN 1992-1-2-2009:
§§2.3, 3.2.2.1, 3.2.3, 3.3.1, 3.4, Figures 3.1/3.3,
Tables 3.1/3.2a, National Annex Table NA.1.

This module gives material curves only, NOT a structural fire-resistance
calculation. No force/load interpolation, buckling, thermal calculation,
spalling, validated advanced numerical model or t_R are implied.

Conventions: mechanical stress in MPa, strain dimensionless, compression
positive for concrete. Steel curve is sign-symmetric. Eurocode concrete
descending branch is chosen as an explicitly permitted *linear* variant.
No extrapolation above 1200 °C. Values with missing stress–strain data
at 1100<theta<1200 °C remain unresolved, even though k_c(theta) itself
is specified by linear interpolation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

VERSION = "R0.6.9D1-TKP-EN1992-1-2-BY-2009-materials-v1"
SOURCE = "ТКП EN 1992-1-2-2009 (02250), EN 1992-1-2:2004 IDT"
NA = "Национальное приложение к ТКП EN 1992-1-2-2009, таблица НП.1"
GAMMA_M_FI = 1.0          # Belarus NA, clause 2.3(2)P
REBAR_FIRE_CLASS = "N"    # Belarus NA, clause 3.2.3(5)
CONDUCTIVITY_NORMAL = "lower_bound"  # Belarus NA, clause 3.3.3(1)

TEMP = (20., 100., 200., 300., 400., 500., 600.,
        700., 800., 900., 1000., 1100., 1200.)
CONCRETE_K = {
    "siliceous": (1., 1., .95, .85, .75, .60, .45, .30, .15, .08, .04, .01, 0.),
    "calcareous": (1., 1., .97, .91, .85, .74, .60, .43, .27, .15, .06, .02, 0.),
}
CONCRETE_EPS_C1 = (.0025, .004, .0055, .007, .010, .015,
                   .025, .025, .025, .025, .025, .025)
CONCRETE_EPS_CU = (.020, .0225, .025, .0275, .030, .0325,
                   .035, .0375, .040, .0425, .045, .0475)

# Table 3.2a, Class N; columns: fsy/fyk, fsp/fyk, Es_theta/Es
STEEL_N = {
    "hot_rolled": {
        "fy": (1.,1.,1.,1.,1.,.78,.47,.23,.11,.06,.04,.02,0.),
        "fp": (1.,1.,.81,.61,.42,.36,.18,.07,.05,.04,.02,.01,0.),
        "E":  (1.,1.,.90,.80,.70,.60,.31,.13,.09,.07,.04,.02,0.),
    },
    "cold_worked": {
        "fy": (1.,1.,1.,1.,.94,.67,.40,.12,.11,.08,.05,.03,0.),
        "fp": (1.,.96,.92,.81,.63,.44,.26,.08,.06,.05,.03,.02,0.),
        "E":  (1.,1.,.87,.72,.56,.40,.24,.08,.06,.05,.03,.02,0.),
    },
}


class EurocodeFireMaterialError(ValueError):
    """Input or source domain does not support the requested state."""


def _positive_finite(value, label):
    if isinstance(value,bool):
        raise EurocodeFireMaterialError(f"{label} must be a positive finite number")
    try: val = float(value)
    except (ValueError, TypeError) as exc:
        raise EurocodeFireMaterialError(f"{label} must be numeric") from exc
    if not math.isfinite(val) or val <= 0:
        raise EurocodeFireMaterialError(f"{label} must be a positive finite number")
    return val


def _temperature(value):
    if isinstance(value,bool):
        raise EurocodeFireMaterialError("temperature must be numeric")
    try: temp=float(value)
    except (TypeError,ValueError) as exc:
        raise EurocodeFireMaterialError("temperature must be numeric") from exc
    if not math.isfinite(temp) or not 20<=temp<=1200:
        raise EurocodeFireMaterialError("source temperature range is 20..1200 °C")
    return temp


def _finite_strain(value):
    if isinstance(value,bool):
        raise EurocodeFireMaterialError("strain must be finite")
    try: eps=float(value)
    except (TypeError,ValueError) as exc:
        raise EurocodeFireMaterialError("strain must be finite") from exc
    if not math.isfinite(eps):
        raise EurocodeFireMaterialError("strain must be finite")
    return eps


def _linear(theta, nodes, values):
    """Literal linear temperature interpolation permitted by §3.2."""
    for i,x in enumerate(nodes):
        if theta==x:
            return float(values[i])
    for i,(lo,hi) in enumerate(zip(nodes,nodes[1:])):
        if lo<theta<hi:
            f=(theta-lo)/(hi-lo)
            return values[i]*(1.-f)+values[i+1]*f
    raise EurocodeFireMaterialError("not tabulated")


@dataclass(frozen=True)
class ConcreteParameters:
    theta_C: float
    aggregate: str
    k_c: float
    eps_c1: float | None
    eps_cu1: float | None
    full_stress_strain_defined: bool
    source: str


def concrete_parameters(theta_C, *, aggregate):
    """Table 3.1. At 1200 °C k=0 but strains are unprovided (—).

    Interpolation 1100<theta<1200 is defined for strength but *not* for
    peak/ultimate strains: their 1200 °C endpoints are absent.
    """
    theta=_temperature(theta_C)
    if aggregate not in CONCRETE_K:
        raise EurocodeFireMaterialError("aggregate must be siliceous or calcareous")
    k=_linear(theta,TEMP,CONCRETE_K[aggregate])
    if theta<=1100:
        eps1=_linear(theta,TEMP[:-1],CONCRETE_EPS_C1)
        epsu=_linear(theta,TEMP[:-1],CONCRETE_EPS_CU)
    else:
        eps1=epsu=None
    return ConcreteParameters(theta,aggregate,k,eps1,epsu,
            theta<=1100 or theta==1200,
            f"{SOURCE} §3.2.2.1, Table 3.1; Fig. 3.1")


def concrete_stress(mechanical_strain,theta_C,*,fck_MPa,aggregate):
    """Figure 3.1 compressive envelope, linear permitted descending branch.

    Returns (signed stress MPa, tangent MPa). Concrete tension ignored as
    explicitly permitted by §3.2.2.2. At 1200 °C zero strength is tabulated.
    1100<theta<1200 is not a full constitutive law (missing eps endpoints).
    """
    e=_finite_strain(mechanical_strain)
    fck=_positive_finite(fck_MPa,"fck_MPa")
    p=concrete_parameters(theta_C,aggregate=aggregate)
    if p.theta_C==1200:
        return 0.,0.
    if not p.full_stress_strain_defined:
        raise EurocodeFireMaterialError(
            "Concrete strain parameters absent in Table 3.1 above 1100 and below 1200 °C")
    f=p.k_c*fck/GAMMA_M_FI
    if e<=0 or e>=p.eps_cu1:
        return 0.,0.
    if e<=p.eps_c1:
        ratio=e/p.eps_c1
        denominator=2.+ratio**3
        stress=3.*f*ratio/denominator
        tangent=3.*f/p.eps_c1*(2.-2.*ratio**3)/denominator**2
        return stress,tangent
    slope=-f/(p.eps_cu1-p.eps_c1)
    return f+slope*(e-p.eps_c1),slope


@dataclass(frozen=True)
class RebarParameters:
    theta_C: float
    production_route: str
    class_N: str
    k_sy: float
    k_sp: float
    k_E: float
    f_sy_MPa: float
    f_sp_MPa: float
    E_s_MPa: float
    eps_sp: float
    eps_sy: float
    eps_st: float
    eps_su: float
    source: str


def reinforcement_parameters(theta_C,*,fyk_MPa,Es_MPa,production_route,
                              ductility_class):
    """Table 3.2a: actual production route and ductility class REQUIRED.

    Belarus NA selects Class N. Class X is not available without tests.
    product_type='weldable_bar' alone cannot establish hot vs cold processing.
    """
    theta=_temperature(theta_C)
    fy=_positive_finite(fyk_MPa,"fyk_MPa")
    Es=_positive_finite(Es_MPa,"Es_MPa")
    if production_route not in STEEL_N:
        raise EurocodeFireMaterialError("production_route hot_rolled/cold_worked must be specified")
    if ductility_class not in ("A","B","C"):
        raise EurocodeFireMaterialError("ductility_class A/B/C must be specified")
    src=STEEL_N[production_route]
    ky=_linear(theta,TEMP,src['fy'])
    kp=_linear(theta,TEMP,src['fp'])
    ke=_linear(theta,TEMP,src['E'])
    fy_t=fy*ky/GAMMA_M_FI
    fp_t=fy*kp/GAMMA_M_FI
    E_t=Es*ke
    esp=fp_t/E_t if E_t>0 else 0.
    eps_st=.05 if ductility_class=='A' else .15
    eps_su=.10 if ductility_class=='A' else .20
    if theta<1200 and not (0<=fp_t<=fy_t and 0<esp<.02):
        raise EurocodeFireMaterialError("inconsistent steel stress–strain parameters")
    return RebarParameters(theta,production_route,"N",ky,kp,ke,
        fy_t,fp_t,E_t,esp,.02,eps_st,eps_su,
        f"{SOURCE} §3.2.3, Table 3.2a; Fig. 3.3; {NA} §3.2.3(5)")


def reinforcement_stress(mechanical_strain,theta_C,*,fyk_MPa,Es_MPa,
                         production_route,ductility_class):
    """Fig. 3.3 material curve incl. rounded transition, plateau and softening.

    Tensile and compressive stress use the same constitutive curve as permitted
    in §3.2.3(4). Does not include bond/slip, bars at 20+ beyond 1200 °C, or
    the explicitly test-dependent Class X material selection.
    """
    ep=_finite_strain(mechanical_strain)
    p=reinforcement_parameters(theta_C,fyk_MPa=fyk_MPa,Es_MPa=Es_MPa,
            production_route=production_route,ductility_class=ductility_class)
    if p.theta_C==1200:
        return 0.,0.
    sign=1. if ep>=0 else -1.
    e=abs(ep)
    if e==0: return 0.,p.E_s_MPa
    if e<=p.eps_sp:
        return sign*p.E_s_MPa*e,p.E_s_MPa
    if e<=p.eps_sy:
        # Algebraically identical to the c,a,b expression of Fig. 3.3.
        d=p.eps_sy-p.eps_sp
        delta=p.f_sy_MPa-p.f_sp_MPa
        if delta==0:
            return sign*p.f_sy_MPa,0.
        denominator=d*p.E_s_MPa-2*delta
        if denominator<=0:
            raise EurocodeFireMaterialError("steel Fig. 3.3 rounded-branch denominator nonpositive")
        c=delta**2/denominator
        a2=d*(d+c/p.E_s_MPa)
        b2=c*d*p.E_s_MPa+c*c
        a=math.sqrt(a2); b=math.sqrt(b2)
        root=math.sqrt(max(0.,a2-(p.eps_sy-e)**2))
        stress=p.f_sp_MPa-c+b*root/a
        tangent=(b*(p.eps_sy-e)/(a*root)) if root>0 else math.inf
        if not math.isfinite(tangent):
            raise EurocodeFireMaterialError("undefined steel tangent")
        return sign*stress,tangent
    if e<=p.eps_st:
        return sign*p.f_sy_MPa,0.
    if e<p.eps_su:
        slope=-p.f_sy_MPa/(p.eps_su-p.eps_st)
        return sign*p.f_sy_MPa*(p.eps_su-e)/(p.eps_su-p.eps_st),slope
    return 0.,0.


def concrete_free_thermal_strain(theta_C,*,aggregate):
    """§3.3.1 temperature elongation relative to 20 °C, tabulated formula."""
    theta=_temperature(theta_C)
    if aggregate=="siliceous":
        return (-1.8e-4+9.e-6*theta+2.3e-11*theta**3) if theta<=700 else .014
    if aggregate=="calcareous":
        return (-1.2e-4+6.e-6*theta+1.4e-11*theta**3) if theta<=805 else .012
    raise EurocodeFireMaterialError("aggregate must be siliceous or calcareous")


def rebar_free_thermal_strain(theta_C):
    """§3.4 hot reinforcing steel only, temperature 20–1200 °C."""
    theta=_temperature(theta_C)
    if theta<=750:
        return -2.416e-4+1.2e-5*theta+0.4e-8*theta**2
    if theta<=860:
        return .011
    return -6.2e-3+2e-5*theta


def qualification():
    """Explicit immutable source choices, not a claim about whole-member ULS."""
    return {
        "version":VERSION,"source":SOURCE,"national_annex":NA,
        "gamma_M_fi":GAMMA_M_FI,"rebar_class":REBAR_FIRE_CLASS,
        "normal_concrete_thermal_conductivity":CONDUCTIVITY_NORMAL,
        "temperature_domain_C":[20,1200],
        "concrete_constitutive_domain_C":[20,1100],
        "concrete_at_1200":"zero_strength_tabulated_strain_parameters_unprovided",
        "concrete_1100_to_1200":"strength_only_strain_curve_unresolved",
        "steel_production_route":"must_be_declared",
        "steel_ductility_class":"must_be_declared",
        "class_X":"not_allowed_without_specific_hot_strength_tests",
        "normative_member_R_t_claim":False,
        "remaining_needs":["qualified thermal calculation using Belarus lower conductivity",
           "concrete 1100-1200 strain-domain treatment",
           "validated N-Mx-My member equilibrium with thermal strains and P-delta",
           "spalling model and actual support/action path",
           "validation against corresponding fire tests per 4.3.4",
        ],
    }
