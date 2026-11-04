#!/usr/bin/env python3
"""K18 DOCX data-binding proof of concept.

Preserves all ZIP members of the original DOCX except word/document.xml, and changes
only w:t nodes inside an explicit allowlist of table cells. Does not recalculate
engineering results, rewrite original prose, or edit OLE formulas.

Usage:
    python report_generator.py generate --template master.docx --data report_data.json --out report.docx
    python report_generator.py check --template master.docx --data report_data.json --xmcd source.xmcd
"""
import argparse, copy, hashlib, json, re, shutil, sys, zipfile
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from lxml import etree
from docx import Document

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DOCXML = 'word/document.xml'

# Locations: (table_number_zero_based, row_number_zero_based, cell_number_zero_based)
PARAGRAPH_FIELDS = {
    "v1.x.N_kN": (91, 2),    # variant 1 force in loads narrative
    "v2.x.N_kN": (93, 1),    # variant 2 force in loads narrative
}
ROW_FIELDS = {
    2: [(3, range(2, 8)), (4, range(2, 8)), (5, range(2, 8)), (6, range(2, 8))],
    3: [(r, range(2, 7)) for r in (3,4,5,6)],
    4: [(2, range(1, 6))],
    5: [(r, range(1, 10)) for r in (3,4,6,7)],
    6: [(r, range(1, 13)) for r in (3,4)],
    7: [(r, range(1, 8)) for r in (3,4,6,7)],
    8: [(r, range(1, 10)) for r in (3,4,6,7)],
    9: [(r, range(1, 13)) for r in (3,4)],
    10: [(r, range(1, 6)) for r in (3,4,6,7)],
    11: [(r, range(1, 9)) for r in (3,4,6,7)],
    12: [(r, range(1, 9)) for r in (2,3,5,6)],
    13: [(r, range(1, 6)) for r in (2,3,5,6)],
    14: [(r, range(1, 5)) for r in (2,3,5,6)],
    15: [(r, range(1, 5)) for r in (2,3,5,6)],
}

def axis_row(r, variant1=(3,4), variant2=(6,7)):
    return ('v1' if r in variant1 else 'v2', 'x' if r in (variant1[0],variant2[0]) else 'y')

def bind_key(t, r, c):
    if t in (14,15):
        v,a = axis_row(r, (2,3), (5,6))
        return f'{v}.{a}.' + {1:'N_kN', 2:'M_Rd_kNm', 3:'M_Ed_kNm', 4:'status'}[c]
    if t==12 and c in (7,8):
        v,a = axis_row(r, (2,3), (5,6))
        return f'{v}.{a}.' + {7:'N_cr_kN_display',8:'eta'}[c]
    if t==13 and c==3:
        v,a=axis_row(r,(2,3),(5,6))
        return f'{v}.{a}.eccentricity_e'
    if t in (5,8):
        v,a=axis_row(r)
        if (t,c) in ((5,2),(8,1)):
            return f'{v}.{a}.bar_diameter_mm'
        if (t,c) in ((5,5),(8,4)):
            return f'{v}.{a}.bar_count'
        if (t,c) in ((5,8),(8,7)):
            return f'{v}.{a}.fy_MPa'
    if t in (6,9) and c<=12:
        a='x' if r==3 else 'y'
        if c in (1,3):return f'fire.{a}.steel_corner_C'
        if c==2:return f'fire.{a}.steel_mid_C'
        return f'fire.{a}.steel_t{c}_C'
    if t==3 and c==6:
        a='x' if r in (3,4) else 'y'
        where='corner' if r in (3,5) else 'mid'
        return f'fire.{a}.steel_{where}_C'
    if t in (7,10) and c in (4,5):
        v,a=axis_row(r)
        return f'{v}.{a}.' + {4:'steel_strength_factor',5:'steel_strength_MPa'}[c]
    return f't{t}.r{r}.c{c}'

def mapping_for_docx(doc):
    slots=defaultdict(list)
    for t, rows in ROW_FIELDS.items():
        for r,cols in rows:
            for c in cols:
                cell=doc.tables[t].cell(r,c)
                slots[bind_key(t,r,c)].append([t,r,c])
    return dict(sorted(slots.items()))

def original_values(doc, slots):
    data={}
    for key,positions in slots.items():
        values=[doc.tables[t].cell(r,c).text.strip() for t,r,c in positions]
        if len(set(values))!=1:
            raise ValueError(f'Conflicting baseline text for slot {key}: {values}')
        data[key]=values[0]
    return data

def template_hash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def build(template, output):
    doc=Document(template)
    slots=mapping_for_docx(doc)
    values=original_values(doc,slots)
    payload={
      'schema':'k18-report-data-v0.1',
      'template_sha256':template_hash(template),
      'report_profile':'K18 two variants / 4-sided heating / R90 / legacy 2025 report',
      'values':values,
      'bindings':slots,
      'provenance':{'baseline':'Пример.docx','calculation':'existing author calculations, not recomputed'},
    }
    Path(output).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload

def decimal_display(text):
    try: return Decimal(text.replace(' ', '').replace(',','.'))
    except Exception:return None

def validate(doc,payload,strict=True):
    errors=[]
    if payload.get('schema')!='k18-report-data-v0.1':errors.append('Unknown payload schema')
    slots=mapping_for_docx(doc)
    if slots != payload.get('bindings'):errors.append('Bindings do not match template')
    values=payload.get('values',{})
    if set(slots)!=set(values):errors.append('Payload does not contain all mapped fields')
    for key,(p,r) in PARAGRAPH_FIELDS.items():
        if doc.paragraphs[p].runs[r].text != original_values(doc,slots).get(key):
            errors.append(f'Baseline prose/table discrepancy for {key}')
    for v in ('v1','v2'):
        for a in ('x','y'):
            n=decimal_display(values.get(f'{v}.{a}.N_kN',''))
            mr=decimal_display(values.get(f'{v}.{a}.M_Rd_kNm',''))
            me=decimal_display(values.get(f'{v}.{a}.M_Ed_kNm',''))
            status=values.get(f'{v}.{a}.status','')
            if None in (n,mr,me) or mr<=0 or n<0:
                errors.append(f'{v}.{a}: invalid load/resistance numbers')
            elif (me<=mr) != (status=='обеспечивается'):
                errors.append(f'{v}.{a}: table status inconsistent with M_Ed <= M_Rd')
        if values.get(f'{v}.x.N_kN')!=values.get(f'{v}.y.N_kN'):
            errors.append(f'{v}: axial force mismatch between X and Y')
        for field in ('bar_diameter_mm','bar_count','fy_MPa'):
            if values.get(f'{v}.x.{field}') != values.get(f'{v}.y.{field}'):
                errors.append(f'{v}: {field} differs between axes, check reinforcement symmetry')
    return errors

def cell_xpath(doc,t,r,c):
    return doc.tables[t].cell(r,c)._tc.getroottree().getpath(doc.tables[t].cell(r,c)._tc)

def insert_values(template, payload, output):
    doc=Document(template)
    errors=validate(doc,payload,strict=False)
    if payload.get('template_sha256')!=template_hash(template):errors.append('Template SHA-256 mismatch')
    if errors:raise ValueError('Report generation blocked:\n - '+'\n - '.join(errors))
    for v in ('v1','v2'):
        for a in ('x','y'):
            if payload['values'][f'{v}.{a}.status']!='обеспечивается':
                raise ValueError('This fixed template asserts R90; failing cases require a separately approved conclusion template')
    slots=payload['bindings']; values=payload['values']
    orig=original_values(doc,slots)
    changed={key:value for key,value in values.items() if value!=orig[key]}
    narrative=payload.get('narrative',{})
    allowed_narrative={'variant1.Mx_kNm':(91,7,'3,83'), 'variant2.Mx_kNm':(93,5,'6,5')}
    if set(narrative)-set(allowed_narrative):
        raise ValueError('Unapproved narrative fields: '+repr(sorted(set(narrative)-set(allowed_narrative))))
    changed_narr={key:value for key,value in narrative.items() if value!=allowed_narrative[key][2]}
    if not changed and not changed_narr:
        shutil.copy2(template,output)
        return {'changed_slots':0,'changed_cell_locations':0,'changed_prose_runs':0,'byte_identical':True}
    with zipfile.ZipFile(template) as z:
        document=etree.fromstring(z.read(DOCXML))
        updated=0
        for key,new_value in changed.items():
            if not isinstance(new_value,str):raise TypeError(f'Slot {key} requires string')
            for t,r,c in slots[key]:
                xp=cell_xpath(doc,t,r,c)
                matches=document.xpath(xp,namespaces=NS)
                if len(matches)!=1:raise ValueError(f'Wrong XML location {key}: {xp}')
                ts=matches[0].xpath('.//w:t',namespaces=NS)
                if not ts:raise ValueError(f'No editable text in {key}: {xp}')
                # Preserve every paragraph, run, cell property and graphic. For multiple
                # text nodes the change may alter character styling; block until mapped.
                original_text=''.join(t.text or '' for t in ts)
                if original_text != orig[key]:
                    raise ValueError(f'Unexpected original cell value for {key}: {original_text!r}')
                if len(ts)==1:
                    ts[0].text=new_value
                elif re.match(r'^[-+]?\d+(?:,\d+)?·10[-+]?\d+$',new_value):
                    # Maintain original superscript run and any independent ·10 run.
                    mant, exponent=new_value.split('·10',1)
                    if len(ts)==2 and (ts[0].text or '').endswith('·10'):
                        ts[0].text=mant+'·10';ts[1].text=exponent
                    elif len(ts)==3 and (ts[1].text or '')=='·10':
                        ts[0].text=mant;ts[1].text='·10';ts[2].text=exponent
                    else:
                        raise ValueError(f'{key}: unsupported scientific-number split')
                elif re.match(r'^[-+]?\d+(?:,\d+)?$',new_value):
                    # Original Word may arbitrarily split digits across w:t nodes.
                    # Retain every run and its formatting; only update its text.
                    positions=[len(t.text or '') for t in ts[:-1]]
                    k=0
                    for node,width in zip(ts[:-1],positions):
                        node.text=new_value[k:k+width];k+=width
                    ts[-1].text=new_value[k:]
                else:
                    raise ValueError(f'{key}: unapproved split text shape')
                updated+=1
        changed_prose=0
        for key,(para_index,run_index) in PARAGRAPH_FIELDS.items():
            if key not in changed:continue
            old_value=doc.paragraphs[para_index].runs[run_index].text
            if old_value!=orig[key]:
                raise ValueError(f'Unexpected original narrative load for {key}: {old_value!r}')
            run=doc.paragraphs[para_index].runs[run_index]._r
            xp=run.getroottree().getpath(run)
            matches=document.xpath(xp,namespaces=NS)
            if len(matches)!=1:raise ValueError(f'Unexpected narrative run location: {xp}')
            ts=matches[0].xpath('.//w:t',namespaces=NS)
            if len(ts)!=1:raise ValueError(f'Unexpected text runs for narrative field {key}')
            ts[0].text=changed[key]
            changed_prose+=1
        for key,new_value in changed_narr.items():
            para_index,run_index,old_text=allowed_narrative[key]
            run=doc.paragraphs[para_index].runs[run_index]
            if run.text!=old_text:raise ValueError('Unexpected original narrative format for '+key)
            xp=run._r.getroottree().getpath(run._r)
            matches=document.xpath(xp,namespaces=NS)
            if len(matches)!=1:raise ValueError('Narrative element missing: '+key)
            ts=matches[0].xpath('.//w:t',namespaces=NS)
            if len(ts)!=1 or ts[0].text!=old_text:raise ValueError('Narrative text changed: '+key)
            ts[0].text=new_value
            changed_prose+=1
        document_bytes=etree.tostring(document,encoding='UTF-8',xml_declaration=True,standalone=True)
        with zipfile.ZipFile(output,'w') as out:
            for info in z.infolist():
                out.writestr(info,document_bytes if info.filename==DOCXML else z.read(info.filename))
    return {'changed_slots':len(changed),'changed_cell_locations':updated,'changed_prose_runs':changed_prose,'byte_identical':False}

def read_xmcd_values(path):
    root=etree.parse(str(path))
    ids={
      'v2.x.N_kN':'25','v2.y.N_kN':'25',
      'v2.x.M_Rd_kNm':'19754','v2.y.M_Rd_kNm':'19910',
      'v2.x.M_Ed_kNm':'504','v2.y.M_Ed_kNm':'2907',
      'v2.x.eta':'1951','v2.y.eta':'2828',
    }
    results={}
    for key,id in ids.items():
        regions=root.xpath(f'//*[local-name()="region" and @region-id="{id}"]')
        if len(regions)!=1:raise ValueError(f'Mathcad region {id} not unique')
        vals=regions[0].xpath('.//*[local-name()="result"]/*[local-name()="real"]/text()')
        if not vals:raise ValueError(f'Mathcad result missing for region {id}')
        results[key]={'region_id':id,'raw':vals[0]}
    return results

def compare_xmcd(payload,path):
    checks=[]
    for key,info in read_xmcd_values(path).items():
        shown=decimal_display(payload['values'][key])
        raw=Decimal(info['raw'])
        decimals=max(0, len(payload['values'][key].split(',')[-1]) if ',' in payload['values'][key] else 0)
        expected=raw.quantize(Decimal(1).scaleb(-decimals),rounding=ROUND_HALF_UP)
        checks.append({**info,'field':key,'display':payload['values'][key],
                       'expected_conventional_rounding':str(expected).replace('.',','),
                       'rounding_match':shown==expected})
    return checks

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--template',required=True);init.add_argument('--out',required=True)
    gen=sub.add_parser('generate');gen.add_argument('--template',required=True);gen.add_argument('--data',required=True);gen.add_argument('--out',required=True)
    chk=sub.add_parser('check');chk.add_argument('--template',required=True);chk.add_argument('--data',required=True);chk.add_argument('--xmcd');chk.add_argument('--out-json')
    args=ap.parse_args()
    try:
        if args.command=='init':
            p=build(args.template,args.out)
            print(json.dumps({'slots':len(p['values']),'targets':sum(map(len,p['bindings'].values()))},ensure_ascii=False))
        elif args.command=='generate':
            data=json.loads(Path(args.data).read_text(encoding='utf-8'))
            print(json.dumps(insert_values(args.template,data,args.out),ensure_ascii=False))
        else:
            data=json.loads(Path(args.data).read_text(encoding='utf-8'))
            errs=validate(Document(args.template),data,strict=False)
            if data.get('template_sha256')!=template_hash(args.template):errs.append('Template hash mismatch')
            checks=compare_xmcd(data,args.xmcd) if args.xmcd else []
            result={'errors':errs,'xmcd_checks':checks}
            if args.out_json:Path(args.out_json).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if errs:sys.exit(2)
    except (ValueError,KeyError,FileNotFoundError,TypeError) as e:
        print(str(e),file=sys.stderr)
        sys.exit(2)

if __name__=='__main__':main()
