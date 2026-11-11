"""SP-R.3 normative-source audit: SP2026 beta*E vs SP5 design parabola tangent.

The temperature-reduced elastic modulus (SP Tables 9/10) and the
initial derivative of the simplified SP5 §6.1.5.4 ULS *section*
parabola are two different source quantities. Do not assert equality,
nor replace the source parabola by an invented hybrid stress curve.
The full SP5 §6.1.5.2 nonlinear diagram and appropriate hot creep/
constitutive validation remain prerequisites for certified P–Delta ULS.
"""
from __future__ import annotations

import math

from rc_fire.materials.normative import ConcreteMix, resolve_materials
from rc_fire.materials.sp2026_fire import concrete_at_sp_fire

VERSION="SP-R3-2026-beta-stiffness-source-audit-v1"
SOURCE="СП 2.02.05-2026 §8.2.18 Table 9; СП 5.03.01-2020 §§6.1.5.2, 6.1.5.4"


def audit_sp2026_concrete_stiffness(column, temperatures_C=(20.,300.,500.,800.)):
    """Quantify source quantities without pretending their ratio is normative ULS."""
    if not isinstance(temperatures_C, (tuple,list)) or not temperatures_C:
        raise ValueError("explicit temperatures required")
    resolved=resolve_materials(column)
    if resolved.get("status")!="resolved_for_property_lookup":
        raise ValueError("SP concrete source material unresolved")
    norm=resolved["concrete"]
    concrete=ConcreteMix(column["concrete"],aggregate_family=resolved["fire_family"])
    eps2=float(norm["eps_c2_permille"])/1000.
    n=float(norm["n_parabola"])
    if eps2<=0 or n<=1:
        raise ValueError("SP5 parabolic law parameters invalid")
    entries=[]
    for t in temperatures_C:
        t=float(t)
        if not math.isfinite(t) or not 20.<=t<=800.:
            raise ValueError("SP Table9 audit requires 20..800 Celsius")
        mat=concrete_at_sp_fire(concrete,t,normal=norm)
        E=float(mat.elastic_modulus_MPa)
        k=float(mat.strength_factor)
        beta=float(mat.modulus_factor)
        tangent=float(n*mat.strength_MPa/eps2)
        entries.append({
            "temperature_C":t,
            "SP_table9_strength_factor_kc":k,
            "SP_table9_elastic_modulus_factor_beta":beta,
            "SP_fire_elastic_modulus_MPa":E,
            "SP5_6_1_5_4_parabolic_initial_tangent_MPa":tangent,
            "initial_tangent_over_reduced_elastic_modulus":tangent/E if E else None,
            "strength_MPa":float(mat.strength_MPa),
            "SP5_eps_c2":eps2, "SP5_n":n,
            "constitutive_section_and_elastic_modulus_are_distinct":True})
    return {
        "version":VERSION,"source":SOURCE,
        "status":"STIFFNESS_MODEL_COMPATIBILITY_REQUIRES_MECHANICAL_QUALIFICATION",
        "samples":entries,
        "source_beta_explicitly_recorded":True,
        "parabolic_tangent_independently_derived":True,
        "stress_curve_silently_refitted_to_beta":False,
        "member_second_order_stiffness_fully_qualified":False,
        "complete_SP5_6_1_5_2_nonlinear_concrete_law_used":False,
        "normative_claim":False}
