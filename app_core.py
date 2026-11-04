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

ROOT = Path(__file__).resolve().parent
SCHEMA_LEGACY = 'k18-independent-engine-v1'
SCHEMA_PARAMETRIC = 'k18-parametric-r04'


def load_example(mode: str) -> dict:
    file_name = 'sample_input.json' if mode == 'legacy' else 'parametric_720x500.json'
    return json.loads((ROOT / 'examples' / file_name).read_text(encoding='utf-8'))


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
    else:
        result = compute_general(GeneralInput.from_dict(payload))
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
        if payload['schema'] == SCHEMA_PARAMETRIC:
            audit = create_report(template, payload, results, target)
            if not audit['footer_parts_unchanged']:
                raise ModelError('Template footer integrity check failed')
            audit['mode'] = 'experimental-parametric'
            audit['certifies_fire_resistance'] = False
        else:
            spec = Inputs.from_dict(payload)
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
