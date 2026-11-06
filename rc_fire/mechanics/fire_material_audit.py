"""R0.6.4C: enforce traceability of heated constitutive input at *all* beam stations.

Closing a code path is not the same as closing its normative qualification.
All unsupported thermal-material assumptions remain conspicuous blockers.
"""
from __future__ import annotations
import math
import numpy as np


def audit_fire_material_stations(laws):
    """All laws must be R0.6.4C fibre laws with original PreparedSection.

    The result documents precisely which parts of the fire material model
    are derived from table nodes versus unqualified numerical conventions.
    """
    if not laws:raise ValueError('no material stations supplied')
    issues=set(); station_summaries=[]
    total_bridge=0;total_concrete_between=0;total_steel_between=0
    from rc_fire.materials.normative import FIRE_TEMP, STEEL_TEMP
    for i,law in enumerate(laws):
        p=getattr(law,'p',None)
        if p is None:raise ValueError('all stations must have real fibre inventory')
        tc=np.asarray(p.concrete_temperature_C,dtype=float)
        ts=np.asarray(p.bar_temperature_C,dtype=float)
        if not len(tc) or not len(ts) or not np.all(np.isfinite(tc)) or not np.all(np.isfinite(ts)):
            raise ValueError('invalid material temperature inventory')
        cb=int(np.sum((ts>20)&(ts<200)))
        concrete_between=int(sum(bool(20<t<800 and not any(abs(t-n)<1e-9 for n in FIRE_TEMP)) for t in tc))
        steel_between=int(sum(bool(200<t<800 and not any(abs(t-n)<1e-9 for n in STEEL_TEMP)) for t in ts))
        total_bridge+=cb;total_concrete_between+=concrete_between;total_steel_between+=steel_between
        if cb:issues.add('STEEL_20_TO_200_BRIDGE_NOT_NORMATIVE')
        if concrete_between or steel_between:issues.add('TEMPERATURE_INTERPOLATION_METHOD_NOT_PRESCRIBED')
        if np.any(tc>20.+1e-8):
            issues.add('HOT_CONCRETE_ULTIMATE_STRAIN_NOT_QUALIFIED')
            issues.add('BETA_ECM_NOT_CONSTITUTIVE_TANGENT')
        if max(float(np.max(tc)),float(np.max(ts)),float(p.boundary_temperature_max_C))>800:
            issues.add('MATERIAL_TABLE_DOMAIN_EXCEEDED')
        if min(float(np.min(tc)),float(np.min(ts)))<20:
            issues.add('MATERIAL_TABLE_DOMAIN_EXCEEDED')
        if p.strength_data.get('reference_strength_mode')!='literal_8_2_18_normative_strength':
            issues.add('FIRE_REFERENCE_STRENGTH_NOT_LITERAL_8_2_18')
        if 'assumed_incremental_integral_not_normative' in getattr(law,'provenance',''):
            issues.add('THERMAL_FREE_STRAIN_INTEGRATION_NOT_QUALIFIED')
        if law.__class__.__name__!='FiberSectionLaw':
            issues.add('MATERIAL_CONSTITUTIVE_LAW_NOT_TYPED')
        station_summaries.append({'index':i,'steel_20_to_200_count':cb,
          'concrete_between_nodes':concrete_between,'steel_between_nodes':steel_between,
          'concrete_max_C':float(np.max(tc)),'steel_min_C':float(np.min(ts)),
          'boundary_max_C':float(p.boundary_temperature_max_C),
          'reference':p.strength_data.get('reference_strength_mode','legacy')})
    # Even at tabulated temperatures, the heated strain laws themselves are
    # not yet validated by a normative ULS comparison/experiment.
    issues.add('SECTION_CONSTITUTIVE_LAW_NOT_NORMATIVELY_QUALIFIED')
    issues.add('FIRE_MATERIAL_R90_VALIDATION_MISSING')
    return {'version':'R0.6.4C-material-evidence-v1',
       'status':'MATERIAL_DATA_AUDITED_NOT_QUALIFIED',
       'count':len(laws),'steel_20_to_200_count':total_bridge,
       'concrete_between_table_nodes_count':total_concrete_between,
       'steel_between_table_nodes_count':total_steel_between,
       'blockers':sorted(issues),'stations':station_summaries,
       'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
