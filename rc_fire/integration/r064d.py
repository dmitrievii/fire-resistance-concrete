"""R0.6.4D optional integration of experimental heated-member ULS evidence.

This module deliberately DOES NOT promote diagnostic results to R90. Each
Gauss and nodal temperature station must be provided explicitly by the user;
no automatic copying of a midspan temperature field along a whole column.
Existing Mathcad/R0.4/R0.5 calculations remain unchanged.
"""
from __future__ import annotations
import copy
import json
import math
from typing import Any

VERSION = 'R0.6.4D-repository-integration-v1'
BLOCKED = 'not_demonstrated'


class MemberEvidenceInputError(ValueError):
    pass


def pending_member_evidence(*, reason='Explicit longitudinal thermal stations and verified fire actions not supplied'):
    return {'version': VERSION, 'status': 'NOT_EVALUATED', 'reason': str(reason),
        'normative_claim': False, 'fire_resistance_status': BLOCKED,
        'blockers': ['EXPLICIT_THERMAL_STATIONS_REQUIRED',
                     'FIRE_ACTIONS_AND_CONSTITUTIVE_QUALIFICATION_REQUIRED']}


def _numeric(v, path, *, lower=None, greater=False):
    if isinstance(v, bool):
        raise MemberEvidenceInputError(f'{path}: finite number required')
    try:
        n=float(v)
    except (ValueError, TypeError) as e:
        raise MemberEvidenceInputError(f'{path}: finite number required') from e
    if not math.isfinite(n) or (lower is not None and (n <= lower if greater else n < lower)):
        raise MemberEvidenceInputError(f'{path}: outside valid finite range')
    return n


def _signature(column):
    # Detect accidental mixing of two buildings/columns along one member.
    # Reinforcement and material specs must agree; thermal exposure may vary by station.
    if not isinstance(column,dict):
        raise MemberEvidenceInputError('full column dictionary required at every station')
    keys=('id','b_mm','h_mm','length_m','concrete','steel_grade','f_y_MPa',
          'bars','material_spec','cover_mm','stirrup_mm',
          'fire_minutes','thermal_spec','mu_x','mu_y','sections')
    data={k:column.get(k) for k in keys}
    for k in ('b_mm','h_mm','length_m','f_y_MPa','cover_mm','stirrup_mm',
              'fire_minutes','mu_x','mu_y'):
        if data[k] is not None:data[k]=float(data[k])
    return json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':'))


def sample_station_bundle(column, *, node_count=3):
    """Create explicit, deliberately INCOMPLETE data template. Never a synthetic fire field."""
    if not isinstance(column,dict):
        raise MemberEvidenceInputError('column dictionary required')
    if not 2 <= int(node_count) <= 21:
        raise MemberEvidenceInputError('node_count must be in 2..21')
    length=_numeric(column.get('length_m'),'column.length_m',lower=0,greater=True)
    z=[length*i/(int(node_count)-1) for i in range(int(node_count))]
    entry={'column':copy.deepcopy(column),'thermal':None}
    return {'schema':'R0.6.4D-explicit-stations-v1',
      'column_id':column.get('id'),'z_m':z,'N_kN':None,
      'gauss_stations':[[copy.deepcopy(entry) for _ in range(3)] for _ in z[:-1]],
      'node_stations':[copy.deepcopy(entry) for _ in z],
      'distributed_load_kNpm':None,
      'fire_actions_source':None,
      'temperature_time_minutes':column.get('fire_minutes'),
      'grid':12,
      'method_notice':'Fill every thermal result and verified fire actions separately; no automatic z-interpolation or R90 approval.'}


def _validate_station_bundle(bundle:dict, *, expected_column=None):
    if not isinstance(bundle,dict) or bundle.get('schema')!='R0.6.4D-explicit-stations-v1':
        raise MemberEvidenceInputError('unsupported or missing station-bundle schema')
    z=bundle.get('z_m')
    if not isinstance(z,list) or not 2<=len(z)<=21:
        raise MemberEvidenceInputError('2..21 longitudinal nodes required')
    zv=[_numeric(x,f'z_m[{i}]') for i,x in enumerate(z)]
    if abs(zv[0])>1e-9 or any(b-a<=0 for a,b in zip(zv,zv[1:])):
        raise MemberEvidenceInputError('z_m must start at zero and increase strictly')
    g=bundle.get('gauss_stations'); nd=bundle.get('node_stations')
    if not isinstance(g,list) or not isinstance(nd,list) or len(g)!=len(z)-1 or len(nd)!=len(z):
        raise MemberEvidenceInputError('complete Gauss and nodal station lists required')
    entries=[]
    for i,row in enumerate(g):
        if not isinstance(row,list) or len(row)!=3:
            raise MemberEvidenceInputError(f'gauss_stations[{i}]: exactly three explicit stations required')
        entries.extend(row)
    entries.extend(nd)
    expected_sig=_signature(expected_column) if expected_column is not None else None
    ids=[]; ref_t=None
    for i,e in enumerate(entries):
        if not isinstance(e,dict) or not isinstance(e.get('column'),dict) or not isinstance(e.get('thermal'),dict):
            raise MemberEvidenceInputError(f'station[{i}]: explicit column and computed thermal object required')
        if e['thermal'].get('status') not in ('evaluated','evaluated_with_scope_warnings'):
            raise MemberEvidenceInputError(f'station[{i}]: evaluated thermal evidence required')
        column=e['column']; t=_numeric(column.get('fire_minutes'),f'station[{i}].fire_minutes',lower=0)
        if ref_t is None:ref_t=t
        if abs(t-ref_t)>1e-8:
            raise MemberEvidenceInputError('all stations must share the same fire-exposure time')
        if expected_sig is not None and _signature(column)!=expected_sig:
            raise MemberEvidenceInputError(f'station[{i}]: column geometry/material differs from selected construction')
        ids.append(column.get('id'))
    if len(set(ids))!=1 or ids[0]!=bundle.get('column_id'):
        raise MemberEvidenceInputError('station column identifiers are inconsistent')
    if expected_column is not None and abs(zv[-1]-_numeric(expected_column.get('length_m'),'length_m'))>1e-7:
        raise MemberEvidenceInputError('member length differs from selected construction')
    n=_numeric(bundle.get('N_kN'),'N_kN',lower=0)
    if expected_column is not None:
        # At present the beam solver assumes CONSTANT axial force N over z.
        # A contradictory multi-section load schedule must not be silently used.
        for sec in expected_column.get('sections',[]):
            ns=sec.get('N_kN')
            if ns is not None and abs(_numeric(ns,'section.N_kN',lower=0)-n)>max(1e-6,1e-7*n):
                raise MemberEvidenceInputError('section axial loads differ from the constant N_kN beam assumption')
    grid=bundle.get('grid',12)
    if type(grid) is not int or not 12<=grid<=64:
        raise MemberEvidenceInputError('grid must be an integer in [12,64]')
    source=bundle.get('fire_actions_source')
    if source is not None and (not isinstance(source,str) or not source.strip()):
        raise MemberEvidenceInputError('fire_actions_source must be non-empty when supplied')
    minutes=bundle.get('temperature_time_minutes')
    if minutes is not None:
        tm=_numeric(minutes,'temperature_time_minutes',lower=0)
        if abs(tm-ref_t)>1e-8:
            raise MemberEvidenceInputError('declared fire time differs from station temperatures')
    return zv,n,grid


def evaluate_explicit_member_bundle(bundle:dict, *, expected_column=None):
    """Run full R0.6.4C only with complete, consistent explicit station data.

    Invalid files are NOT converted to a reassuring successful result.
    Only supported user-supplied boundary conditions may be used: the solver's
    pinned/pinned default is explicitly marked diagnostic, not verified supports.
    """
    z,n,grid=_validate_station_bundle(bundle,expected_column=expected_column)
    from rc_fire.member import EndSupport, run_heated_member_uls_evidence
    def support(key):
        value=bundle.get(key, {'kind':'pinned'})
        if not isinstance(value,dict) or value.get('kind') not in ('pinned','fixed','free','guided','elastic'):
            raise MemberEvidenceInputError(f'{key}: explicit supported kind required')
        # default pinned is diagnostic and does not imply actual structure's boundary condition
        from rc_fire.member import CoupledMemberError
        try:
            support_obj=EndSupport(**value)
            support_obj.validate()
            return support_obj
        except (TypeError,ValueError,CoupledMemberError) as exc:
            raise MemberEvidenceInputError(f'{key}: {exc}') from exc
    l=support('left_support');r=support('right_support')
    result=run_heated_member_uls_evidence(z,n,
      gauss_stations=bundle['gauss_stations'],node_stations=bundle['node_stations'],
      left=l,right=r,grid=grid,
      distributed_load_kNpm=bundle.get('distributed_load_kNpm'),
      nodal_forces=bundle.get('nodal_forces'),
      initial_imperfection=bundle.get('initial_imperfection'),
      fire_actions_source=bundle.get('fire_actions_source'),
      temperature_time_minutes=bundle.get('temperature_time_minutes'),
      strength_mode='literal_8_2_18_normative_strength')
    if not isinstance(result,dict):
        raise RuntimeError('unknown member response')
    # Strict fail-closed wrapper: even unexpected inherited claims cannot pass.
    return {**result,'version':VERSION,'normative_claim':False,
            'fire_resistance_status':BLOCKED,
            'integration_status':'DIAGNOSTIC_ONLY',
            'source_member_version':result.get('version')}


def attach_member_evidence(result:dict, *, bundle=None, expected_column=None):
    """Non-mutating adapter for the existing column result facade."""
    if not isinstance(result,dict):
        raise MemberEvidenceInputError('legacy result must be dictionary')
    if result.get('normative_claim') is True or result.get('fire_resistance_status') not in (None,'not_demonstrated'):
        raise MemberEvidenceInputError('cannot attach diagnostics to a previously certified result')
    out=dict(result)
    if bundle is None:
        out['member_r064d']=pending_member_evidence()
    else:
        out['member_r064d']=evaluate_explicit_member_bundle(bundle, expected_column=expected_column)
    # Never override any of the historical calculations or internal mechanical result.
    out['normative_claim']=False
    out['fire_resistance_status']=BLOCKED
    return out
