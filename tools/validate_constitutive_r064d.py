"""R0.6.4D reproducible material-law audit (NOT normative qualification)."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

from rc_fire.materials.normative import (FIRE_TEMP, CONCRETE_K, CONCRETE_BETA,
                                         STEEL_TEMP,STEEL_GROUPS)
from rc_fire.mechanics.normative import (concrete_parabolic_linear,steel_bilinear)


def evaluate_materials():
    """Use exactly tabulated temperatures; do not infer missing normative points."""
    fck=30.;fcd=25.;Ecm=33000.;eps2=.002;n=2.;fyk=500.;Es=200000.
    concrete=[];steel=[]
    for i,t in enumerate(FIRE_TEMP):
        k=float(CONCRETE_K['siliceous'][i]);beta=float(CONCRETE_BETA['siliceous'][i])
        fc=fck*k
        et=1.e-5
        s,d=concrete_parabolic_linear(et,fc,eps2,.0035,n)
        h=1e-8
        sp,_=concrete_parabolic_linear(et+h,fc,eps2,.0035,n)
        sm,_=concrete_parabolic_linear(et-h,fc,eps2,.0035,n)
        dfd=(float(sp)-float(sm))/(2*h)
        if not np.isclose(float(d),dfd,rtol=1e-6,atol=1e-3):
            raise AssertionError(f'concrete tangent mismatch at {t} C')
        concrete.append({'temperature_C':float(t),'kc':k,'beta_c':beta,
            'fck_kc_MPa':fc,'legacy_fcd_kc_MPa':fcd*k,
            'tabulated_beta_Ecm_GPa':beta*Ecm/1000,
            'stress_law_initial_tangent_GPa':n*fc/eps2/1000,
            'stress_law_tangent_at_1e-5_GPa':float(d)/1000,
            'finite_difference_tangent_GPa':dfd/1000,
            'initial_tangent_to_beta_Ecm':float(n*fc/eps2/(beta*Ecm))})
    for i,t in enumerate(STEEL_TEMP):
        k=float(STEEL_GROUPS['S240_S500']['k'][i]);beta=float(STEEL_GROUPS['S240_S500']['beta'][i])
        fy=fyk*k;E=Es*beta
        et=1e-5
        s,d=steel_bilinear(et,fy,E)
        h=1e-8
        sp,_=steel_bilinear(et+h,fy,E)
        sm,_=steel_bilinear(et-h,fy,E)
        dfd=(float(sp)-float(sm))/(2*h)
        if not np.isclose(float(d),dfd,rtol=1e-7,atol=1e-3):
            raise AssertionError(f'steel tangent mismatch at {t} C')
        steel.append({'temperature_C':float(t),'ks':k,'beta_s':beta,
                      'fy_theta_MPa':fy,'Es_theta_GPa':beta*Es/1000,
                      'finite_difference_tangent_GPa':dfd/1000})
    return {'source':'СП 2.02.05-2026 §8.2.18, tables 9 and 10; '
          'СП 5.03.01-2020 (6.17)-(6.18) for ambient concrete diagram',
        'qualification':'NOT_QUALIFIED_FIRE_ULS',
        'concrete':concrete,'steel':steel,
        'steel_20_200_C':'UNDEFINED_BY_TABULATED_NODES',
        'hot_eps_cu2':'NOT_ESTABLISHED_BY_CITED_TABLES',
        'compatibility_betaEcm_vs_concrete_tangent':'NOT_ESTABLISHED',
        'normative_claim':False,'fire_resistance_status':'not_demonstrated'}


if __name__=='__main__':
    r=evaluate_materials()
    out=Path(__file__).resolve().parents[1]/'R064D_CONSTITUTIVE_VALIDATION.json'
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: finite difference constitutive tangents at',len(r['concrete']),
          'concrete nodes and',len(r['steel']),'steel nodes')
    print('R0.6.4D: NOT_QUALIFIED_FIRE_ULS; JSON=',out)
