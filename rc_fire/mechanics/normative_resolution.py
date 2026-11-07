"""R0.6.3C source-anchored constitutive adjudication, not a certification.

All temperatures in degrees Celsius; strengths/moduli in MPa. Primary sources:
SP 2.02.05-2026 8.2.16-8.2.19, Tables 9-12 (PDF pp. 38-39);
SP 5.03.01-2020 4.2.5.3, Table 4.6, 6.1.5.2-4 (PDF pp. 61-62).

Do NOT use ambient material coefficients as silently adopted elevated-temperature
ultimate strains. Do NOT infer a concrete parabola's tangent from beta Ecm.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Sequence
from .constitutive_qualification import concrete_table_evidence, steel_table_evidence

SOURCE_FIRE_STRENGTH = 'СП 2.02.05-2026, §8.2.18: расчётные сопротивления = нормативные значения × k(θ)'
SOURCE_RC_DESIGN = 'СП 5.03.01-2020, §4.2.5.3 таблица 4.6, §6.1.2.11, (6.4)-(6.5), (6.28)'
SOURCE_RC_STRAIN = 'СП 5.03.01-2020, §6.1.5.4, (6.17)-(6.18), таблица 6.1'

@dataclass(frozen=True)
class NormativeDecision:
    code: str
    resolution: str
    normative_status: str
    evidence: str
    engineering_consequence: str


def elevated_strength_comparison(*, theta_C: float, concrete_family: str,
                                 steel_group: str, fck_MPa: float, fcd_MPa: float,
                                 fyk_MPa: float, fyd_MPa: float) -> dict:
    """Calculate both competing fire-strength bases; no silent equivalence.

    At 20<T<200, steel Table 10 is unavailable: do not invent ks.  The
    concrete comparison is still returned for all temperatures in Table 9.
    """
    vals=(theta_C,fck_MPa,fcd_MPa,fyk_MPa,fyd_MPa)
    if not all(math.isfinite(float(v)) for v in vals):
        raise ValueError('All temperatures and strengths must be finite')
    if min(fck_MPa,fcd_MPa,fyk_MPa,fyd_MPa)<=0:
        raise ValueError('Strengths must be positive')
    c=concrete_table_evidence(theta_C,concrete_family)
    out={'temperature_C':float(theta_C), 'source':SOURCE_FIRE_STRENGTH,
         'concrete':{'kc':c.k_strength,'tabular_provenance':c.provenance,
             'literal_SP_8_2_18_MPa':fck_MPa*c.k_strength,
             'legacy_accidental_fcd_times_kc_MPa':fcd_MPa*c.k_strength,
             'difference_MPa':(fck_MPa-fcd_MPa)*c.k_strength,
             'ratio_literal_to_legacy':fck_MPa/fcd_MPa},
         'steel':None,'normative_claim':False}
    try:
        s=steel_table_evidence(theta_C,steel_group)
    except ValueError:
        out['steel_status']='TABLE_10_NO_DEFINED_COEFFICIENT'
    else:
        out['steel']={'ks':s.k_strength,'tabular_provenance':s.provenance,
                      'literal_SP_8_2_18_MPa':fyk_MPa*s.k_strength,
                      'legacy_accidental_fyd_times_ks_MPa':fyd_MPa*s.k_strength}
        out['steel_status']='ambient_reference' if theta_C==20 else 'table_10_evaluated'
    return out


def constitutive_closure_decisions(*, concrete_temperatures_C:Sequence[float],
                                   steel_temperatures_C:Sequence[float],
                                   concrete_family:str, steel_group:str,
                                   fck_MPa:float,fcd_MPa:float,fyk_MPa:float,
                                   fyd_MPa:float,Ecm_MPa:float,eps_c2:float,
                                   n:float) -> dict:
    """Evaluated source decisions with explicit blocking unresolved questions.

    No false assumption that this table audit supplies an elevated-temperature
    complete stress-strain model or solves member-level fire resistance.
    """
    ct=[float(v) for v in concrete_temperatures_C]
    st=[float(v) for v in steel_temperatures_C]
    if not ct or not st or any(not math.isfinite(v) for v in ct+st):
        raise ValueError('Nonempty finite temperature vectors required')
    if not math.isfinite(Ecm_MPa) or Ecm_MPa<=0 or eps_c2<=0 or n<=1:
        raise ValueError('Invalid mechanical properties')
    # Representative material strength comparison at a listed node, chosen as
    # 500 C only if actual concrete temperatures attain it; otherwise the max
    # within the defined Table 9 range.  No extrapolation for any temperature.
    sampled=max(ct)
    example=min(800.,max(20.,sampled))
    comp=elevated_strength_comparison(theta_C=example,
        concrete_family=concrete_family,steel_group=steel_group,
        fck_MPa=fck_MPa,fcd_MPa=fcd_MPa,fyk_MPa=fyk_MPa,fyd_MPa=fyd_MPa)
    beta=concrete_table_evidence(example,concrete_family).beta_modulus
    tangent_legacy=(n*fcd_MPa*comp['concrete']['kc']/eps_c2)
    stiffness={'temperature_C':example,'beta_Ecm_MPa':None if beta is None else beta*Ecm_MPa,
        'parabola_initial_tangent_legacy_MPa':tangent_legacy,
        'same_quantity':False,
        'constitutive_stiffness_verified':False}
    decisions=[
      NormativeDecision('C01_FIRE_STRENGTH_REFERENCE',
        '§8.2.18 explicitly says normative material values × k(θ); retain separate literal branch and legacy γ-based result',
        'TEXT_RESOLVED_IMPLEMENTATION_NOT_REQUALIFIED',SOURCE_FIRE_STRENGTH+'; '+SOURCE_RC_DESIGN,
        'Do not use legacy fcd*k as an unqualified normative design resistance'),
      NormativeDecision('C02_STEEL_BELOW_200',
        'Table 10 starts at 200 °C; no interpolation rule from 20 °C is supplied in the cited clause',
        'NO_NORMATIVE_BRIDGE',SOURCE_FIRE_STRENGTH+'; table 10',
        '20<T<200 °C uses a named diagnostic bridge only; block qualified claim'),
      NormativeDecision('C03_HOT_CONCRETE_STRAINS',
        'The implemented SP fire Table 9 gives k and β, but no hot eps_c2, eps_cu2 or n',
        'NOT_QUALIFIED',SOURCE_RC_STRAIN+'; СП 2.02.05-2026 table 9',
        'Room-temperature ultimate strains are diagnostic assumptions only'),
      NormativeDecision('C04_BETA_TANGENT',
        'β Ecm is a reduced elastic modulus, not automatically the initial tangent of ambient-shaped (6.17)',
        'NOT_QUALIFIED',SOURCE_FIRE_STRENGTH+'; '+SOURCE_RC_STRAIN,
        'No mechanically consistent heated constitutive stiffness validated for second-order analysis'),
      NormativeDecision('C05_FREE_THERMAL_STRAIN',
        'SP §8.2.19 supplies expansion/shrinkage coefficients; free thermal strain not applied in 3-DOF section solver',
        'NOT_IMPLEMENTED','СП 2.02.05-2026 §8.2.19 tables 11-12, equation (6)',
        'Do not represent total strain as mechanical strain in restrained member checks'),
    ]
    return {'version':'R0.6.3C-source-adjudication-v1',
       'status':'PARTIAL_TEXTUAL_CLOSURE_NO_CONSTITUTIVE_QUALIFICATION',
       'normative_claim':False,'fire_resistance_status':'not_demonstrated',
       'decisions':[asdict(d) for d in decisions],
       'strength_comparison':comp,'stiffness_comparison':stiffness,
       'temperature_domain':{'concrete_min_C':min(ct),'concrete_max_C':max(ct),
          'steel_min_C':min(st),'steel_max_C':max(st)},
       'steel_bars_needing_non_normative_bridge':sum(20<t<200 for t in st),
       'unresolved_codes':[d.code for d in decisions if d.normative_status not in ('TEXT_RESOLVED_IMPLEMENTATION_NOT_REQUALIFIED',)],
       'source_documents':[SOURCE_FIRE_STRENGTH,SOURCE_RC_DESIGN,SOURCE_RC_STRAIN]}
