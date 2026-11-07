"""R0.6.3B — auditable material-law qualification; NO normative R(t) claim.

The user-provided primary sources are SP 2.02.05-2026, 8.2.18-19,
Tables 9-12, and SP 5.03.01-2020, 6.1.5 and 6.2.2.13.

This module deliberately separates exact table-node replication from a
numerical interpolation agreement, and explicitly identifies unresolved
reference-strength and hot-strain rules. Its result NEVER certifies R90.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Sequence
from rc_fire.materials.normative import (
    FIRE_TEMP, CONCRETE_K, CONCRETE_BETA, STEEL_TEMP, STEEL_GROUPS
)

SOURCE_FIRE = 'СП 2.02.05-2026 §8.2.18, таблицы 9-10; §8.2.19, таблицы 11-12'
SOURCE_RC = 'СП 5.03.01-2020 таблица 4.6, (6.4)-(6.5), (6.17)-(6.18), (6.28)'


@dataclass(frozen=True)
class CoefficientEvidence:
    temperature_C: float
    k_strength: float
    beta_modulus: float | None
    provenance: str
    source: str


def _coeff_at(theta:float, temps:Sequence[float], kvals:Sequence[float],
              bvals:Sequence[float] | None, source:str) -> CoefficientEvidence:
    t=float(theta)
    if not math.isfinite(t) or t < temps[0] or t > temps[-1]:
        raise ValueError(f'T={t} °C outside [{temps[0]}, {temps[-1]}] °C tabular domain')
    for i,at in enumerate(temps):
        if t == at:
            return CoefficientEvidence(t,float(kvals[i]),
                None if bvals is None else float(bvals[i]),'exact_table_node',source)
    for i in range(1,len(temps)):
        if t < temps[i]:
            w=(t-temps[i-1])/(temps[i]-temps[i-1])
            k=kvals[i-1]+w*(kvals[i]-kvals[i-1])
            beta=None if bvals is None else bvals[i-1]+w*(bvals[i]-bvals[i-1])
            return CoefficientEvidence(t,float(k), None if beta is None else float(beta),
                                       'engineering_linear_between_nodes',source)
    raise AssertionError('unreachable')


def concrete_table_evidence(theta_C:float, family:str) -> CoefficientEvidence:
    """Normative ordinates at nodes, explicit *engineering* interpolation between."""
    if family not in CONCRETE_K:raise ValueError('unrecognized Table 9 family')
    return _coeff_at(theta_C,FIRE_TEMP,CONCRETE_K[family],
                     CONCRETE_BETA.get(family),SOURCE_FIRE+' / 9')


def steel_table_evidence(theta_C:float, group:str) -> CoefficientEvidence:
    """No invented 20--200 °C rule; 20 °C is a separate ambient reference.

    Temperature 20 is taken from normal RC properties, *not* Table 10.
    Between 20 and 200 degrees the caller must use a labeled non-normative
    bridge, or reject, rather than misrepresent the data as tabulated.
    """
    if group not in STEEL_GROUPS:raise ValueError('unrecognized Table 10 group')
    t=float(theta_C)
    if not math.isfinite(t):raise ValueError('nonfinite temperature')
    if t==20:
        return CoefficientEvidence(20.,1.,1.,'ambient_reference_not_table_10',SOURCE_RC)
    if 20<t<200:
        raise ValueError('temperature 20..200 °C: no Table 10 ordinate or prescribed bridge')
    dat=STEEL_GROUPS[group]
    return _coeff_at(t,STEEL_TEMP,dat['k'],dat['beta'],SOURCE_FIRE+' / 10')


def steel_bridge_diagnostic(theta_C:float,group:str) -> CoefficientEvidence:
    """Non-normative bridge reproducing the existing R0.6.3 linear scheme."""
    t=float(theta_C)
    if not (20<t<200):raise ValueError('diagnostic bridge only for 20<T<200')
    dat=STEEL_GROUPS[group]
    w=(t-20.)/180.
    return CoefficientEvidence(t,1.+w*(dat['k'][0]-1.),
                  1.+w*(dat['beta'][0]-1.),
                  'non_normative_linear_bridge_ambient_to_200',SOURCE_RC+'; '+SOURCE_FIRE)


def assess_constitutive_qualification(*, concrete_temperatures_C:Sequence[float],
    steel_temperatures_C:Sequence[float], concrete_family:str, steel_group:str,
    ambient_fck_MPa:float, ambient_fcd_MPa:float,
    include_high_temp_diagnostic:bool=False, boundary_max_C:float | None=None) -> dict:
    """Explicit scientific qualification gate for constitutive inputs.

    Evaluated independently of a successful Newton equilibrium solution.
    No inference is made that 20--200 °C steel or heated ultimate concrete
    strains are normatively covered by the implemented constitutive law.
    """
    if concrete_family not in CONCRETE_K or steel_group not in STEEL_GROUPS:
        raise ValueError('invalid concrete/steel table family')
    tc=[float(v) for v in concrete_temperatures_C]
    ts=[float(v) for v in steel_temperatures_C]
    if not tc or not ts or any(not math.isfinite(x) for x in tc+ts):
        raise ValueError('finite, nonempty temperature vectors required')
    issues=[]
    steel_bridge=sum(20<t<200 for t in ts)
    steel_between=sum(200<t<800 and t not in STEEL_TEMP for t in ts)
    concrete_between=sum(20<t<800 and t not in FIRE_TEMP for t in tc)
    above=sum(t>800 for t in tc+ts)
    if boundary_max_C is not None and not math.isfinite(float(boundary_max_C)):
        raise ValueError("nonfinite boundary temperature")
    outside_boundary=bool(boundary_max_C is not None and boundary_max_C>800)
    below=sum(t<20 for t in tc+ts)
    hot_concrete=any(t>20 for t in tc)
    if above or below or outside_boundary:issues.append('MATERIAL_TABLE_OUTSIDE_20_800')
    if steel_bridge:issues.append('STEEL_20_200_NO_NORMATIVE_BRIDGE')
    if steel_between or concrete_between:issues.append('INTERPOLATION_METHOD_NOT_EXPLICITLY_PRESCRIBED')
    if hot_concrete:issues.append('HOT_CONCRETE_ULTIMATE_STRAINS_UNQUALIFIED')
    if hot_concrete:issues.append('FREE_THERMAL_STRAIN_NOT_APPLIED_IN_SECTION_EQUILIBRIUM')
    # The Table 9 factors beta Ecm are distinct from tangent of (6.17)-(6.18).
    issues.append('CONCRETE_BETA_ECM_NOT_CONSTITUTIVE_TANGENT')
    # 8.2.18 literally refers to normative strengths; SP 5.03.01 accidental
    # partial factors supply a competing design-strength reading. Explicitly
    # preserve both until an authoritative clause-by-clause adjudication.
    if not (ambient_fck_MPa>0 and ambient_fcd_MPa>0):
        raise ValueError('positive reference strengths required')
    issues.append('REFERENCE_STRENGTH_FCK_VERSUS_FCD_UNADJUDICATED')
    causes=sorted(set(issues))
    if below or ((above or outside_boundary) and not include_high_temp_diagnostic):
        status='OUTSIDE_SUPPORTED_TEMPERATURE_DOMAIN'
    elif above or outside_boundary:
        status='DIAGNOSTIC_ABOVE_TABLE_RANGE'
    else:
        status='ENGINEERING_DIAGNOSTIC_NOT_NORMATIVELY_QUALIFIED'
    return {
      'status':status,'normative_claim':False,'fire_resistance_status':'not_demonstrated',
      'reference_strength_options_MPa':{'characteristic_fck':float(ambient_fck_MPa),
           'design_fcd':float(ambient_fcd_MPa),
           'ratio_fck_over_fcd':ambient_fck_MPa/ambient_fcd_MPa},
      'counts':{'concrete_fibers':len(tc),'steel_bars':len(ts),
        'steel_bridge_20_200':steel_bridge,'steel_between_table_nodes':steel_between,
        'concrete_between_table_nodes':concrete_between,
        'above_800':above,'boundary_samples_above_800':int(outside_boundary),'below_20':below},
      'temperature_ranges_C':{'concrete':[min(tc),max(tc)],'steel':[min(ts),max(ts)], 'boundary_max_C':boundary_max_C},
      'hot_concrete_strains':'ambient_eps_c2_eps_cu2_used_for_diagnostic_only',
      'concrete_beta_Ecm':'reported_not_used_to_rescale_parabolic_tangent',
      'reference_strength':'design_fcd_used_current_solver; characteristic_fck_alternative_unresolved',
      'issues':causes,'source_documents':[SOURCE_FIRE,SOURCE_RC]
    }
