"""Full value map from independent calculation to fixed K18 Word table slots.

The master Word is structurally immutable. This module only prepares the existing
267 bound values and a small allowlist of narrative values. Unsupported report
changes are blocked rather than delivering stale/misleading prose or images.
"""
from __future__ import annotations
from decimal import Decimal,ROUND_DOWN,ROUND_HALF_UP,ROUND_CEILING,ROUND_FLOOR
from pathlib import Path
import json,re,copy
from calculation_engine import Inputs,ModelError,compute
import word_patch

SCI=re.compile(r'^([+-]?\d+(?:,\d+)?)·10([+-]?\d+)$')
NUM=re.compile(r'^([+-]?\d+)(?:,(\d+))?$')
ROUNDING=[('nearest',ROUND_HALF_UP),('truncate',ROUND_DOWN),('ceil',ROUND_CEILING),('floor',ROUND_FLOOR)]

def formatted(value:float, sample:str, rule):
    v=Decimal(str(value))
    s=SCI.fullmatch(sample)
    if s:
        n=len(s.group(1).split(',')[1]) if ',' in s.group(1) else 0
        exp=int(s.group(2))
        m=v/(Decimal(10)**exp)
        q=Decimal('1').scaleb(-n)
        return f'{m.quantize(q,rounding=rule):f}'.replace('.',',')+'·10'+s.group(2)
    s=NUM.fullmatch(sample)
    if not s:raise ModelError(f'Not a numeric Word field: {sample!r}')
    d=len(s.group(2)) if s.group(2) else 0
    q=Decimal('1').scaleb(-d)
    return f'{v.quantize(q,rounding=rule):f}'.replace('.',',')


def bound_values(result:dict):
    """Numerical data for all changeable existing table slots."""
    th=result['thermal']; cc={}
    def put(k,v):
        if k in cc:
            if abs(cc[k]-v)>1e-9:raise ModelError(f'Conflicting mapped value {k}')
        else: cc[k]=float(v)
    def c(t,r,col,n):put(f't{t}.r{r}.c{col}',n)
    for ax in ('x','y'):
        for key,value in (('steel_corner_C',th['reported_steel_temperatures_C'][0]),('steel_mid_C',th['reported_steel_temperatures_C'][1])):
            put(f'fire.{ax}.{key}',value)
    for row,offset in ((3,0),(4,1),(5,0),(6,1)):
        for col,value in enumerate(th['x_points_m'][offset],2):c(2,row,col,value)
        c(2,row,6,th['a_red_m2_h']);c(2,row,7,th['l_m'])
        for col,value in enumerate(th['r_points'][offset],2):c(3,row,col,value)
    for col,value in enumerate([result['inputs']['fire']['concrete_critical_C'],th['r_1'],th['delta_m'],th['r_corner'],th['l_corner_m']],1):c(4,2,col,value)
    geometry=result['inputs']['geometry']; material=result['inputs']['material']
    for varid in ('v1','v2'):
        v=result['variants'][varid]
        for ax in ('x','y'):
            a=v['axes'][ax]
            tbl_r= {'v1':{'x':3,'y':4},'v2':{'x':6,'y':7}}[varid][ax]
            stiffness_r={'v1':{'x':2,'y':3},'v2':{'x':5,'y':6}}[varid][ax]
            put(f'{varid}.{ax}.bar_diameter_mm',a['bar_diameter_mm'])
            put(f'{varid}.{ax}.bar_count',a['bar_count'])
            put(f'{varid}.{ax}.fy_MPa',a['f_y_MPa'])
            put(f'{varid}.{ax}.steel_strength_factor',a['k_steel'])
            put(f'{varid}.{ax}.steel_strength_MPa',a['fyd_MPa'])
            put(f'{varid}.{ax}.N_kN',a['N_kN'])
            put(f'{varid}.{ax}.M_Rd_kNm',a['M_Rd_kNm'])
            put(f'{varid}.{ax}.M_Ed_kNm',a['M_Ed_kNm'])
            put(f'{varid}.{ax}.N_cr_kN_display',a['N_cr_kN'])
            put(f'{varid}.{ax}.eta',a['eta'])
            put(f'{varid}.{ax}.eccentricity_e',a['e_0_m'])
            # T5: steel geometry; T7: beta and E; T8: compression geometry.
            c(5,tbl_r,9,geometry['c_y_m'] if ax=='x' else geometry['c_x_m'])
            c(7,tbl_r,6,a['beta_steel'])
            c(7,tbl_r,7,a['E_steel_GPa'])
            c(8,tbl_r,8,geometry['c_y_m'] if ax=='x' else geometry['c_x_m'])
            c(8,tbl_r,9,material['f_ck_MPa'])
            # T11: reduced cross-section and strain/neutral axis.
            for col,val in enumerate([a['effective_width_m'],a['web_width_m'],a['d_fi_m'],a['x_eff_m'],
                                       a['eps_cu2_permille'],a['eps_sy_permille'],a['xi_lim'],a['xi_dfi_m']],1):c(11,tbl_r,col,val)
            # T12: slenderness / nominal stiffness (existing table uses doubled steel inertia).
            for col,val in enumerate([a['lambda'],a['kc'],a['I_c_m4'],1,a['I_s_total_m4'],a['B_Nm2']],1):c(12,stiffness_r,col,val)
            # T13: eccentricties. e0 is separate shared key at c3.
            for col,val in {1:a['e_a1_m'],2:a['e_a2_m'],4:a['e_m'],5:a['e_s_m']}.items():c(13,stiffness_r,col,val)
    return cc


def require_fixed_template(spec:Inputs,result:dict):
    """Prevent false R90 or stale figures/physical description."""
    g=spec.geometry;f=spec.fire;m=spec.material;mechan=spec.mechanics
    defaults=[('b_m',g.b_m,.6),('h_m',g.h_m,.6),('length_m',g.length_m,13.7),
              ('c_x_m',g.c_x_m,.05),('c_y_m',g.c_y_m,.05),
              ('delta_extra',g.reduction_delta_extra_m,.034),('A_c_correction',g.section_area_correction_m2,.032),
              ('a_red',f.a_red_m2_h,.00133),('phi_1',f.phi_1,.63),('phi_2',f.phi_2,.5),
              ('critical_C',f.concrete_critical_C,500),('ambient_C',f.ambient_C,20),
              ('ref_steel_d',f.steel_reference_diameter_m,.025),('f_ck',m.f_ck_MPa,30),
              ('fy',m.f_y_MPa,500),('E_cm',m.E_cm_GPa,29),('E_s',m.E_s_GPa,200),
              ('eps_cu2',m.eps_cu2_permille,3.5),
              ('mu_x',mechan.mu_x,.8),('mu_y',mechan.mu_y,1.2),
              ('ea2x',mechan.e_a2x_m,.023),('ea2y',mechan.e_a2y_m,.020),
              ('phi100',mechan.phi_100_30_35,2.2),('alpha_cs',mechan.alpha_cs,.79),
              ('ks',mechan.k_ks,1),('diam_minor_y',mechan.minor_inertia_d_y_mm,16),
              ('compress_d_x',mechan.compression_d_x_mm,.001),('compress_d_y',mechan.compression_d_y_mm,.01),
              ('compress_count',mechan.compression_count,2),('compress_temp',mechan.compression_temperature_C,410),
              ('mperm',mechan.creep_m_perm_kNm,10),
              ('mtotal',mechan.creep_m_total_kNm,16)]
    changed=[f'{name}: {val} != {expected}' for name,val,expected in defaults if abs(val-expected)>1e-10]
    if f.faces!=4 or f.minutes!=90:changed.append('Only original four-sided R90 report supported')
    if changed:raise ModelError('Fixed Word report cannot represent changed geometry/material/fire: '+'; '.join(changed))
    expected={'v1':20,'v2':25}
    for v in spec.variants:
        if v.M_x_kNm<0:
            raise ModelError('The positive-Mx fixed narrative cannot display negative initial moments safely')
        if v.bars_per_face!=3 or v.bar_diameter_mm!=expected[v.id]:
            raise ModelError(f'Fixed Word drawings require {v.id} = 3 bars Ø{expected[v.id]}')
        if v.M_y_kNm!=0:
            raise ModelError('Existing Word prose and drawings do not declare a nonzero y-axis initial moment')
        if not all(result['variants'][v.id]['axes'][ax]['pass'] for ax in ('x','y')):
            raise ModelError(f'{v.id} does not satisfy original separate axis checks; fixed positive R90 conclusion forbidden')


def build_payload(spec:Inputs,result:dict,baseline:dict)->tuple[dict,dict]:
    require_fixed_template(spec,result)
    payload=copy.deepcopy(baseline)
    computed=bound_values(result)
    # Learn each field's original rounding convention from the immutable K18 reference,
    # independently of the current (possibly changed) input values.
    reference_path=Path(__file__).resolve().parent/'sample_input.json'
    reference_spec=Inputs.from_dict(json.loads(reference_path.read_text(encoding='utf-8')))
    reference_fields=bound_values(compute(reference_spec))
    rounding_profile={}
    for key,ref in reference_fields.items():
        original=baseline['values'][key]
        matched_rule=next((tag for tag,rule in ROUNDING if formatted(ref,original,rule)==original),None)
        if matched_rule is None:
            raise ModelError(f'No deterministic rounding profile for {key}: {ref} versus {original!r}')
        rounding_profile[key]=matched_rule
    matched=[];changed=[]
    for key,value in computed.items():
        if key not in payload['values']:
            raise ModelError('Word field not registered: '+key)
        original=payload['values'][key]
        tag=rounding_profile[key]
        chosen=(tag,formatted(value,original,dict(ROUNDING)[tag]))
        if chosen[1] == original:matched.append({'field':key,'value':original,'rounding':chosen[0]})
        else:changed.append({'field':key,'original':original,'computed':chosen[1],'rounding':chosen[0]})
        payload['values'][key]=chosen[1]
    # Section-dimension strings are also derived from model inputs, though currently
    # unchanged by the fixed-K18 report contract.
    section=f"{round(spec.geometry.b_m*1000)}×{round(spec.geometry.h_m*1000)}"
    for row in (3,4,6,7):
        k=f't5.r{row}.c1'
        if payload['values'][k]!=section:raise ModelError('Fixed section description no longer matches calculation')
        payload['values'][k]=section
    # Preserve blank '-' fields and fixed table structure, but do not call these calculated.
    for v in ('v1','v2'):
        for a in ('x','y'):
            payload['values'][f'{v}.{a}.status']='обеспечивается'
    # Existing report has a numeric narrative for both initial Mx variants.
    def fmt_mx(k,old):
        v=Decimal(str(k))
        decimals=len(old.split(',')[1]) if ',' in old else 0
        return f'{v.quantize(Decimal(1).scaleb(-decimals),rounding=ROUND_HALF_UP):f}'.replace('.',',')
    payload['narrative']={'variant1.Mx_kNm':fmt_mx(result['variants']['v1']['axes']['x']['M0_kNm'],'3,83'),
                          'variant2.Mx_kNm':fmt_mx(result['variants']['v2']['axes']['x']['M0_kNm'],'6,5')}
    payload['provenance']={'calculation':'Independent Python K18 legacy reconstruction v0.3',
                           'not_from_xmcd_saved_results':True,
                           'master':'Original provided report preserved as frozen master',
                           'scope':'Only fixed R90 two-variant profile and existing drawings'}
    info={'dynamic_fields':len(computed)+4,'unchanged_fields':len(payload['values'])-len(computed)-4,
          'aligned_with_original':len(matched),'differences':changed,
          'unmapped_original_fields':sorted(set(payload['values'])-set(computed)-{f't5.r{row}.c1' for row in (3,4,6,7)}),
          'rounding_profile':rounding_profile,
          'notes':['Some fields (symbols, blank slots, fixed prose) are deliberately preserved',
                   'Mathcad/report coordinate x12 conflict remains in saved XMCD but report baseline is adopted']}
    return payload,info

