"""Pure backend for a session-isolated Streamlit front end.

No global mutable state. The reference Word template is supplied by the user per
request and is never written to the source repository or shared cache.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import tempfile
from typing import Any

from calculation_engine import Inputs, ModelError, compute
from parametric_engine import GeneralInput, compute_general
from parametric_report import create_report
from report_adapter import build_payload
from word_patch import insert_values
from reinforcement_layout import infer_perimeter, active_definition

ROOT = Path(__file__).resolve().parent
SCHEMA_LEGACY = 'k18-independent-engine-v1'
SCHEMA_PARAMETRIC = 'k18-parametric-r04'


def load_example(mode: str = 'k18') -> dict:
    """One parametric input schema. K18 is the default, not a separate UI mode.

    Kept `legacy`/`parametric` aliases for existing regression tests and imports.
    """
    if mode in ('k18', 'default'):
        return legacy_to_parametric(json.loads((ROOT / 'examples' / 'sample_input.json').read_text(encoding='utf-8')))
    file_name = 'sample_input.json' if mode == 'legacy' else 'parametric_720x500.json'
    return json.loads((ROOT / 'examples' / file_name).read_text(encoding='utf-8'))


def legacy_to_parametric(old: dict) -> dict:
    """Convert an original K18 input into editable bars, without changing loads.

    Only the reference K18 geometry/cover can be assumed; these bars are the
    eight distinct perimeter positions in drawing 9–9 (3 per exterior face).
    """
    Inputs.from_dict(old)
    g=old['geometry'];b=float(g['b_m']);h=float(g['h_m'])
    cx=float(g['c_x_m']);cy=float(g['c_y_m'])
    coords=[(cx,cy),(b/2,cy),(b-cx,cy),(cx,h/2),(b-cx,h/2),
            (cx,h-cy),(b/2,h-cy),(b-cx,h-cy)]
    return {
      'schema':SCHEMA_PARAMETRIC,
      'geometry':{'b_m':b,'h_m':h,'length_m':float(g['length_m'])},
      'material':{key:float(old['material'][key]) for key in ('f_ck_MPa','E_cm_GPa','f_y_MPa','E_s_GPa')},
      'fire':{'minutes':old['fire']['minutes'], 'exposed_faces':['left','right','bottom','top'],
              'a_red_m2_h':old['fire']['a_red_m2_h'],'phi_1':old['fire']['phi_1'],
              'phi_2':old['fire']['phi_2'],
              'critical_concrete_C':old['fire']['concrete_critical_C']},
      'mechanics':{'mu_x':old['mechanics']['mu_x'],'mu_y':old['mechanics']['mu_y']},
      'variants':[{ 'id':v['id'],'N_kN':v['N_kN'],'M_x_kNm':v['M_x_kNm'],
        'M_y_kNm':v['M_y_kNm'],
        'bars':[{'id':str(i+1),'x_m':x,'y_m':y,
                 'diameter_mm':v['bar_diameter_mm']} for i,(x,y) in enumerate(coords)],
        'reinforcement':{'mode':'perimeter','basis':'edges','symmetric':True,
           'nx':3,'ny':3,'diameter_mm':float(v['bar_diameter_mm']),
           'left_mm':cx*1000,'right_mm':cx*1000,
           'bottom_mm':cy*1000,'top_mm':cy*1000,
           'spacing_x_mm':(b-2*cx)*500,'spacing_y_mm':(h-2*cy)*500}}
        for v in old['variants']]
    }


def reference_compatible(payload: dict) -> bool:
    """Exact geometric/method applicability gate; loads may vary within bounds.

    A modified input must never inherit static Mathcad numerical results.
    """
    if payload.get('schema')!=SCHEMA_PARAMETRIC:
        return False
    ref=load_example('k18')
    def near(a,b):
        return math.isfinite(float(a)) and abs(float(a)-float(b)) <= 1e-9
    for group in ('geometry','material','mechanics'):
        if any(not near(payload[group].get(k,float('nan')),v) for k,v in ref[group].items()):
            return False
    for k,v in ref['fire'].items():
        if k=='exposed_faces':
            if payload['fire'].get(k)!=v:return False
        elif not near(payload['fire'].get(k,float('nan')),v):return False
    if len(payload.get('variants',[]))!=2:return False
    for current,baseline in zip(payload['variants'],ref['variants']):
        if current.get('id')!=baseline['id']:return False
        if not near(current.get('M_y_kNm',float('nan')),0) or current.get('M_x_kNm',-1)<0:return False
        if len(current.get('bars',[]))!=len(baseline['bars']):return False
        actual=sorted((round(float(b['x_m']),9),round(float(b['y_m']),9),
                       round(float(b['diameter_mm']),9)) for b in current['bars'])
        expected=sorted((round(float(b['x_m']),9),round(float(b['y_m']),9),
                         round(float(b['diameter_mm']),9)) for b in baseline['bars'])
        if actual!=expected:return False
    return True


def _legacy_from_parametric(payload: dict) -> dict:
    if not reference_compatible(payload):
        raise ModelError('K18 reference calculations require the exact K18 section and steel pattern')
    old=load_example('legacy')
    for v in old['variants']:
        p=next(x for x in payload['variants'] if x['id']==v['id'])
        for key in ('N_kN','M_x_kNm','M_y_kNm'):
            v[key]=float(p[key])
    return old


def validate_json_payload(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise ModelError('The input must be a JSON object')
    schema = payload.get('schema')
    if schema == SCHEMA_LEGACY:
        Inputs.from_dict(payload)
    elif schema == SCHEMA_PARAMETRIC:
        GeneralInput.from_dict(payload)
    else:
        raise ModelError('Unsupported input schema')
    return payload


def execute(payload: dict) -> dict:
    validate_json_payload(payload)
    if payload['schema'] == SCHEMA_LEGACY:
        result = compute(Inputs.from_dict(payload))
    elif reference_compatible(payload):
        # An internal solver choice, never a second user-facing mode.
        result = compute(Inputs.from_dict(_legacy_from_parametric(payload)))
        result['method_label']='K18 Mathcad-reproducing calculation'
        result['source_note']='K18 v2 compared against XMCD; v1 compared against the original report.'
    else:
        result = compute_general(GeneralInput.from_dict(payload))
        result['method_label']='Experimental parametric fiber-section calculation'
        result['source_note']='Not a Mathcad result; no normative biaxial fire verification.'
    try:
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ModelError('Solver produced non-finite values; report generation disabled') from exc
    return result


def summary_rows(result: dict) -> list[dict]:
    rows = []
    for v, detail in result['variants'].items():
        for axis in ('x', 'y'):
            a = detail['axes'][axis]
            rows.append({
                'Variant': v, 'Axis': axis.upper(),
                'N [kN]': round(float(a.get('N_kN', detail.get('N_kN', 0))), 3),
                'MEd [kNm]': round(float(a['M_Ed_kNm']), 3),
                'MRd [kNm]': round(float(a['M_Rd_kNm']), 3),
                'η': round(float(a['eta']), 4),
                'Utilization': round(float(a['utilization']), 4),
                'Single-axis pass': bool(a['pass']),
            })
    return rows


def _assert_reference_template(template_bytes: bytes) -> None:
    if len(template_bytes) > 12 * 1024 * 1024:
        raise ModelError('Template is too large (12 MB limit)')
    baseline = json.loads((ROOT / 'data_baseline.json').read_text(encoding='utf-8'))
    if sha256(template_bytes).hexdigest() != baseline['template_sha256']:
        raise ModelError('This is not the original approved K18 template. Upload the exact Пример.docx from the R0.4 package.')


def generate_docx(payload: dict, results: dict, template_bytes: bytes) -> tuple[bytes, dict]:
    """Generate a report using only temporary per-call files.

    Caller must provide the original exact template; both paths never persist.
    """
    validate_json_payload(payload)
    _assert_reference_template(template_bytes)
    with tempfile.TemporaryDirectory(prefix='k18_report_') as td:
        folder = Path(td)
        template = folder / 'reference.docx'
        target = folder / 'report.docx'
        template.write_bytes(template_bytes)
        if results.get('engine') == 'k18-parametric-experimental':
            audit = create_report(template, payload, results, target)
            if not audit['footer_parts_unchanged']:
                raise ModelError('Template footer integrity check failed')
            audit['mode'] = 'experimental-parametric'
            audit['certifies_fire_resistance'] = False
        else:
            spec = (Inputs.from_dict(payload) if payload['schema']==SCHEMA_LEGACY
                    else Inputs.from_dict(_legacy_from_parametric(payload)))
            base = json.loads((ROOT / 'data_baseline.json').read_text(encoding='utf-8'))
            report_payload, audit = build_payload(spec, results, base)
            insert_values(template, report_payload, target)
            audit['mode'] = 'reference-K18'
        result_bytes = target.read_bytes()
    return result_bytes, audit


def compact_json_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def bars_table(payload: dict, variant_index: int) -> list[dict]:
    v = payload['variants'][variant_index]
    return [
        {'ID': str(b['id']), 'X [mm]': float(b['x_m']) * 1000,
         'Y [mm]': float(b['y_m']) * 1000, 'Diameter [mm]': float(b['diameter_mm'])}
        for b in v['bars']
    ]


def parse_bars_table(rows: list[dict]) -> list[dict]:
    bars = []
    for i, row in enumerate(rows):
        if all((v is None or str(v).strip() == '') for v in row.values()):
            continue
        if any((v is None or str(v).strip() == '') for v in row.values()):
            raise ModelError(f'Bar row {i+1}: incomplete data')
        try:
            bars.append({'id': str(row['ID']), 'x_m': float(row['X [mm]'])/1000,
                         'y_m': float(row['Y [mm]'])/1000,
                         'diameter_mm': float(row['Diameter [mm]'])})
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelError(f'Bar row {i+1}: invalid values') from exc
    return bars


def with_variant_count(payload: dict, count: int) -> dict:
    if payload['schema'] != SCHEMA_PARAMETRIC:
        raise ModelError('Variant count available only for parametric mode')
    if not 1 <= count <= 12:
        raise ModelError('Require 1–12 variants')
    out = deepcopy(payload)
    while len(out['variants']) < count:
        v = deepcopy(out['variants'][-1])
        v['id'] = f'v{len(out["variants"])+1}'
        out['variants'].append(v)
    out['variants'] = out['variants'][:count]
    return out


def input_fingerprint(payload:dict)->str:
    """Stable session fingerprint: numerically equal 90 and 90.0 are identical.

    Streamlit number_input returns floats even when the example uses JSON ints.
    Without normalization the initial K18 results would incorrectly appear stale.
    """
    def norm(x):
        if isinstance(x,bool):return x
        if isinstance(x,(int,float)):
            return round(float(x),12)
        if isinstance(x,dict):return {k:norm(v) for k,v in x.items()}
        if isinstance(x,list):return [norm(v) for v in x]
        return x
    return sha256(json.dumps(norm(payload),ensure_ascii=False,sort_keys=True,
                          separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
