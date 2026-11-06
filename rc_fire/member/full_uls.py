"""R0.6.4C end-to-end *diagnostic* ULS evidence; no automatic R90.

Every Gauss section and every member node MUST be supplied with its own
explicit thermal input. There is no assumption of uniform heating along the
column, nor a hidden interpolation of the temperature history or actions.
"""
from __future__ import annotations
import numpy as np

from .coupled import (EndSupport, FiberSectionLaw, CoupledMemberError,
    solve_coupled_beam, heated_laws_from_explicit_thermal_stations,
    integrated_free_strains_diagnostic)
from .uls import audit_heated_member_uls
from rc_fire.mechanics.fire_material_audit import audit_fire_material_stations


def _node_law_from_explicit_station(entry, *, grid, strength_mode):
    from rc_fire.mechanics.normative import prepare_section
    from rc_fire.mechanics.fire_strength import select_fire_reference_strength
    from rc_fire.thermal import temperature_rectangle, RectangularExposure
    if not isinstance(entry,dict) or 'column' not in entry or 'thermal' not in entry:
        raise CoupledMemberError('node must have explicit column and thermal data')
    c=entry['column'];th=entry['thermal']
    if abs(float(c['fire_minutes'])-float(th['fire_minutes']))>1e-9:
        raise CoupledMemberError('node fire minutes inconsistent')
    if set(c['thermal_spec']['exposed_faces'])!=set(th['exposed_faces']):
        raise CoupledMemberError('node fire-face exposure inconsistent')
    p=prepare_section(c,th,grid=grid,above_800_policy='reject')
    p,_=select_fire_reference_strength(p,mode=strength_mode)
    ex=RectangularExposure(c['b_mm'],c['h_mm'],tuple(th['exposed_faces']))
    cb,_=temperature_rectangle(ex,th['coefficients'],c['fire_minutes'],
        np.asarray([b['x_mm'] for b in c['bars']],dtype=float),
        np.asarray([b['y_mm'] for b in c['bars']],dtype=float))
    cx=np.array([0.,c['b_mm'],0.,c['b_mm']])
    cy=np.array([0.,0.,c['h_mm'],c['h_mm']])
    corner_theta,_=temperature_rectangle(ex,th['coefficients'],c['fire_minutes'],cx,cy)
    f=integrated_free_strains_diagnostic(p,concrete_at_bars_C=cb,
        concrete_at_corners_C=corner_theta,
        source_provenance='СП 2.02.05-2026 §8.2.19; numerical integral assumed',
        accept_integration_convention=True)
    return FiberSectionLaw(p,free_concrete=f['free_concrete'],
        free_steel=f['free_steel'],free_concrete_at_bars=f['free_concrete_at_bars'],
        free_concrete_at_corners=f['free_concrete_at_corners'],
        provenance=f['provenance'])


def run_heated_member_uls_evidence(z_m,N_kN,*,gauss_stations,node_stations,
    left=EndSupport('pinned'),right=EndSupport('pinned'),
    distributed_load_kNpm=None,nodal_forces=None,initial_imperfection=None,
    grid=12,fire_actions_source=None,temperature_time_minutes=None,
    strength_mode='literal_8_2_18_normative_strength'):
    """Explicit Annex K → fibre/eigenstrain → 2-axis beam → ULS audit.

    This is a sampled first/second-order numerical validation workflow. It
    DOES NOT automatically qualify a complete resistance against fire.
    The caller supplies all Gauss and nodal temperature sections independently.
    """
    z=np.asarray(z_m,dtype=float)
    if z.ndim!=1 or len(z)<2 or not np.all(np.isfinite(z)) or np.any(np.diff(z)<=0):
        raise CoupledMemberError('invalid member stations')
    if len(gauss_stations)!=len(z)-1 or len(node_stations)!=len(z):
        raise CoupledMemberError('one 3-point Gauss row per element AND one thermal station per node required')
    from rc_fire.mechanics.normative import SectionMechanicsError
    from rc_fire.materials import MaterialError
    try:
        thermal=heated_laws_from_explicit_thermal_stations(gauss_stations,grid=grid,
            accept_integration_convention=True,strength_mode=strength_mode)
        nodal_laws=[_node_law_from_explicit_station(e,grid=grid,strength_mode=strength_mode)
                    for e in node_stations]
    except (SectionMechanicsError,MaterialError,CoupledMemberError,ValueError) as exc:
        return {'version':'R0.6.4C-coupled-member-uls-evidence-v1',
                'status':'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT',
                'reason':str(exc),'normative_claim':False,
                'fire_resistance_status':'not_demonstrated',
                'blockers':['MATERIAL_OR_TEMPERATURE_INPUT_NOT_QUALIFIED']}
    all_material_laws=[thermal['law_at_gauss'](i,j) for i in range(len(z)-1) for j in range(3)]+nodal_laws
    material_audit=audit_fire_material_stations(all_material_laws)
    r=solve_coupled_beam(z,N_kN,law_at_gauss=thermal['law_at_gauss'],
        left=left,right=right,distributed_load_kNpm=distributed_load_kNpm,
        nodal_forces=nodal_forces,initial_imperfection=initial_imperfection)
    uls=audit_heated_member_uls(r,z,N_kN,node_laws=nodal_laws,
        action_provenance=fire_actions_source,
        material_provenance='SP 8.2.18 literal strength; constitutive/thermal laws still diagnostic',
        temperature_time_minutes=temperature_time_minutes,
        axial_restraint_qualified=False,spalling_qualified=False)
    uls['blockers']=sorted(set(uls.get('blockers',[])+material_audit['blockers']))
    return {'version':'R0.6.4C-coupled-member-uls-evidence-v1',
       'status':uls['status'],'member':r,'uls':uls,
       'thermal_station_count':sum(len(row) for row in gauss_stations)+len(node_stations),
       'material_strength_mode':strength_mode,
       'thermal_provenance':thermal['evidence'],
       'material_audit':material_audit,
       'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
