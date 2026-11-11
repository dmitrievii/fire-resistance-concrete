"""Small source-preserving input adapter for the public R0.7 column screen.

These are actual geometry, composition and fire-design actions. None are
computed by backfilling a private Mathcad example, and no trial load is
silently assigned. The canonical project_model remains the only validated
source for all downstream engines.
"""
from __future__ import annotations

import math
from multicolumn_r05.project_model import new_column

VERSION="R0.7-simple-physical-column-inputs-v1"


def _finite(x, title, *, positive=False):
    if isinstance(x,bool):
        raise ValueError(f"{title}: numeric value required")
    try: v=float(x)
    except (TypeError,ValueError) as exc:
        raise ValueError(f"{title}: numeric value required") from exc
    if not math.isfinite(v) or (positive and v<=0):
        raise ValueError(f"{title}: positive finite value required" if positive
                         else f"{title}: finite value required")
    return v


def perimeter_bars(*,b_mm,h_mm,cover_mm,tie_d_mm,bar_d_mm,
                   bars_horizontal,bars_vertical):
    """Explicit evenly spaced perimeter bars; keep corner bars unique."""
    b=_finite(b_mm,'b_mm',positive=True)
    h=_finite(h_mm,'h_mm',positive=True)
    cover=_finite(cover_mm,'cover',positive=True)
    tie=_finite(tie_d_mm,'stirrup',positive=True)
    dia=_finite(bar_d_mm,'bar diameter',positive=True)
    if type(bars_horizontal) is not int or type(bars_vertical) is not int:
        raise ValueError('bar count along each side must be an integer')
    if not 2<=bars_horizontal<=20 or not 2<=bars_vertical<=20:
        raise ValueError('bars per edge must be between 2 and 20')
    offset=cover+tie+dia/2
    if not offset<b/2 or not offset<h/2:
        raise ValueError('cover, stirrup and bar diameter exceed section geometry')
    sx=(b-2*offset)/(bars_horizontal-1)
    sy=(h-2*offset)/(bars_vertical-1)
    if sx<dia or sy<dia:
        raise ValueError('reinforcement bars overlap along perimeter')
    pts=[]
    for j in range(bars_horizontal):
        pts.append((offset+j*sx,offset))
    for i in range(1,bars_vertical-1):
        pts.append((b-offset,offset+i*sy))
    for j in reversed(range(bars_horizontal)):
        pts.append((offset+j*sx,h-offset))
    for i in reversed(range(1,bars_vertical-1)):
        pts.append((offset,offset+i*sy))
    return [{'id':f'S{i+1}','x_mm':round(x,7),'y_mm':round(y,7),
             'diameter_mm':dia} for i,(x,y) in enumerate(pts)]


def make_column(inputs:dict):
    """Convert exactly stated construction/material/action data to public core."""
    if not isinstance(inputs,dict):
        raise ValueError('input dictionary required')
    numeric=('b_mm','h_mm','length_m','cover_mm','stirrup_mm',
        'bar_diameter_mm','dry_density_kg_m3','coarse_aggregate_pct',
        'max_aggregate_mm','cement_kg_m3','water_cement_ratio',
        'relative_humidity_pct','required_minutes','N_kN',
        'Mx_kNm','My_kNm')
    v={}
    for k in numeric:
        v[k]=_finite(inputs.get(k),k,positive=not k.startswith('M') and
                     k not in ('relative_humidity_pct',))
    if not 250<=v['b_mm']<=2000 or not 250<=v['h_mm']<=2000:
        raise ValueError('section dimensions must be 250..2000 mm')
    if not 1<=v['length_m']<=40:
        raise ValueError('length must be 1..40 m')
    if not 0<v['coarse_aggregate_pct']<=100:
        raise ValueError('coarse aggregate volume fraction must be >0 and <=100%')
    if not 0<v['relative_humidity_pct']<=100:
        raise ValueError('relative humidity must be 0..100%')
    if not inputs.get('exposed_faces'):
        raise ValueError('select at least one fire-exposed face')
    route=inputs.get('steel_route')
    duct=inputs.get('ductility_class')
    if route not in ('hot_rolled','cold_worked'):
        raise ValueError('steel manufacturing route must be explicitly stated')
    if duct not in ('A','B','C'):
        raise ValueError('steel ductility class A/B/C must be explicitly stated')
    cls=inputs.get('concrete_class')
    if cls not in ('C20/25','C25/30','C30/37','C35/45','C40/50'):
        raise ValueError('unsupported concrete strength class')
    family=inputs.get('aggregate_family')
    if family not in ('siliceous','calcareous'):
        raise ValueError('concrete aggregate family must be declared')
    consistency=inputs.get('consistency')
    if consistency not in ('V3_V4','V1_V2','S1_S2','S3_S5'):
        raise ValueError('concrete consistency must be declared')
    curing=inputs.get('curing')
    if curing not in ('natural','heat'):
        raise ValueError('curing method must be declared')
    if type(inputs.get('natural_sand_confirmed')) is not bool:
        raise ValueError('actual natural-sand classification must be stated')
    modulus_basis=inputs.get('modulus_aggregate')
    measured_Ecm=inputs.get('measured_Ecm_GPa')
    if modulus_basis=='gravel_granite_upto40':
        if family!='siliceous':
            raise ValueError('Do not label calcareous aggregate as granite for Ecm')
        if measured_Ecm is not None:
            raise ValueError('Select either laboratory Ecm or source Table 6.3 basis')
    else:
        if measured_Ecm is None:
            raise ValueError('For non-gravel/granite aggregate, Ecm from tests must be given')
        measured_Ecm=_finite(measured_Ecm,'measured_Ecm_GPa',positive=True)
    c=new_column(1)
    c.update({
        'name':str(inputs.get('name') or 'К1').strip(),
        'b_mm':v['b_mm'],'h_mm':v['h_mm'],'length_m':v['length_m'],
        'concrete':cls,'steel_grade':'S500',
        'f_y_MPa':500.,'E_s_GPa':200.,
        'cover_mm':v['cover_mm'],'stirrup_mm':v['stirrup_mm'],
        'bar_diameter_mm':v['bar_diameter_mm'],
        'mu_x':_finite(inputs.get('mu_x',1.),'mu_x',positive=True),
        'mu_y':_finite(inputs.get('mu_y',1.),'mu_y',positive=True),
        'fire_minutes':v['required_minutes'],'bar_mode':'manual'})
    if inputs.get('bars') is not None:
        bars=inputs['bars']
        if not isinstance(bars,list) or len(bars)<4:
            raise ValueError('manual bar list must contain at least four bars')
        c['bars']=[{'id':str(bar['id']),'x_mm':_finite(bar['x_mm'],'bar.x'),
                 'y_mm':_finite(bar['y_mm'],'bar.y'),
                 'diameter_mm':_finite(bar['diameter_mm'],'bar.d',positive=True)}
                  for bar in bars]
    else:
        c['bars']=perimeter_bars(b_mm=v['b_mm'],h_mm=v['h_mm'],
            cover_mm=v['cover_mm'],tie_d_mm=v['stirrup_mm'],
            bar_d_mm=v['bar_diameter_mm'],
            bars_horizontal=int(inputs.get('bars_horizontal',3)),
            bars_vertical=int(inputs.get('bars_vertical',3)))
    c['sections']=[{
        'id':'center','name':'Расчётное сечение',
        'z_m':v['length_m']/2,'auto_midspan':True,
        'N_kN':v['N_kN'],'Mx_kNm':v['Mx_kNm'],'My_kNm':v['My_kNm']}]
    c['material_spec']={
        'concrete':{'aggregate_family':family,
            'consistency':consistency,'curing':curing,
            'modulus_aggregate':modulus_basis if modulus_basis=='gravel_granite_upto40'
                                else None,
            **({'independently_measured_Ecm_GPa':measured_Ecm}
               if measured_Ecm is not None else {})},
        'steel':{'product_type':'weldable_bar'}}
    c['thermal_spec']={
        'a_red_mode':'table_K1','exposed_faces':list(inputs['exposed_faces']),
        'concrete_family':family,'dry_density_kg_m3':v['dry_density_kg_m3'],
        'moisture_mass_pct':_finite(inputs['moisture_mass_pct'],
            'moisture_mass_pct')}
    c['annex_l_spec']={
        'natural_sand_confirmed':inputs['natural_sand_confirmed'],
        'coarse_aggregate_volume_pct':v['coarse_aggregate_pct'],
        'max_aggregate_mm':v['max_aggregate_mm'],
        'relative_humidity_pct':v['relative_humidity_pct'],
        'cement_kg_m3':v['cement_kg_m3'],
        'water_cement_ratio':v['water_cement_ratio'],
        'moisture_mode':'auto'}
    # Metadata must not be placed inside the strictly validated Appendix L
    # parameter schema. Keep human-provenance separate from physical inputs.
    # Manufacturing choice is used only by the TKP steel law through
    # explicit fire_assessment arguments. It is NOT part of the separate
    # SP normal-temperature Reinforcement dataclass/schema.
    steel_confirmed=inputs.get('steel_material_confirmed') is True
    c['source_assumptions']={
        'natural_sand':inputs.get('natural_sand_provenance','user_declared'),
        'steel_manufacturing_route':route,
        'steel_ductility_class':duct,
        'steel_material_confirmed':steel_confirmed,
        'steel_selection_provenance':(
            'user_documented' if steel_confirmed
            else 'user_visible_demonstration_defaults_unconfirmed'),
    }
    # This is a **section input**, not proof of the complete longitudinal
    # member load distribution. Effective length factors alone cannot
    # establish the actual end supports or eliminate lateral sway.
    c['member_spec']={
        'thermal_longitudinal_mode':'explicit_only',
        'load_mode':'not_defined'}
    return c


def explicit_pinned_uniform_sp2026_member(column, *,
    confirmed_pinned_uniform_action_model, confirmed_uniform_longitudinal_fire,
    imperfection_x_mm, imperfection_y_mm):
    """Opt-in, restricted *physical* beam load model for a public SP-R3 case.

    First-order midspan moments are created exclusively by uniform q on a
    pinned-pinned beam: Mx,mid=q_x*L²/8 and My,mid=q_y*L²/8.
    The user must affirm this schematic: general end moments, N eccentricity
    or frame effects CANNOT be inferred from one midspan N/Mx/My.
    Initial geometry is an explicit 2-axis half-sine imperfection with
    amplitude entered in mm (NOT an automatically normative SP5 value).
    """
    if (confirmed_pinned_uniform_action_model is not True or
            confirmed_uniform_longitudinal_fire is not True):
        raise ValueError("SP-R3 requires explicit confirmation of action diagram and full-length heating")
    if not isinstance(column,dict):
        raise ValueError("physical column is required")
    L=_finite(column.get("length_m"),"column length",positive=True)
    if abs(_finite(column.get("mu_x"),"mu_x")-1.)>1.e-8 or abs(
           _finite(column.get("mu_y"),"mu_y")-1.)>1.e-8:
        raise ValueError("Pinned-pinned UI model requires mu_x=mu_y=1; other supports need full member specification")
    ss=column.get("sections") or []
    if len(ss)!=1 or abs(float(ss[0].get("z_m",-1.))-L/2.)>1.e-8:
        raise ValueError("Pinned-uniform UI model requires the sole midspan load section")
    N=_finite(ss[0].get("N_kN"),"fire N",positive=True)
    mx=_finite(ss[0].get("Mx_kNm"),"first-order Mx")
    my=_finite(ss[0].get("My_kNm"),"first-order My")
    ex=_finite(imperfection_x_mm,"initial x imperfection")/1000.
    ey=_finite(imperfection_y_mm,"initial y imperfection")/1000.
    if not 0<=ex<=L/10. or not 0<=ey<=L/10.:
        raise ValueError("explicit geometric imperfection outside 0..L/10")
    def shape(amp):
        slope=math.pi*amp/L
        return [0.,slope,amp,0.,0.,-slope]
    times=[float(column["fire_minutes"])*frac/3. for frac in (1.,2.,3.)]
    if not all(abs(round(t/5.)*5.-t)<1.e-8 for t in times):
        # SP-R2 public history stores five-minute temperatures. Do not
        # interpolate unsolved times or invent a recorded snapshot.
        times=[float(column["fire_minutes"])]
    return {
        "load_mode":"explicit_sp2026_beam",
        "z_m":[0.,L/2.,L],
        "N_kN":N,
        "left_support":{"x":"pinned","y":"pinned"},
        "right_support":{"x":"pinned","y":"pinned"},
        "axial_restraint_mode":"free_axial_expansion",
        "fire_design_action_source":"user-entered already combined fire action N and first-order midspan M",
        "distributed_load_kNpm":[[8.*mx/(L*L),8.*my/(L*L)] for _ in range(3)],
        "nodal_forces":[0.]*12,
        "transverse_action_source":"user-confirmed pinned-pinned, uniform q from FIRST-ORDER midspan M=qL²/8",
        "initial_imperfection":shape(ex)+shape(ey),
        "imperfection_source":"user-entered x/y amplitudes; half-sine initial shape; NOT an SP5-certified imperfection magnitude",
        "entered_section_moments_reconciled":True,
        "longitudinal_thermal_mode":"explicit_uniform_full_length",
        "uniform_exposure_confirmed":True,
        "history_times_minutes":times}
