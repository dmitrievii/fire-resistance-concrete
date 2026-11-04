"""Print-ready, self-contained HTML for an immediate report without a DOCX master.

No JavaScript/network/CSS assets are fetched. Values always come from the
executed calculation object (not displayed inputs or cached reference numbers).
"""
from __future__ import annotations
from html import escape
from datetime import date
from section_drawing import section_svg, steel_legend, bar_schedule
from reinforcement_layout import definition_rows


def _fmt(value:float,digits:int=3)->str:
    return f'{float(value):,.{digits}f}'.replace(',',' ')


def make_printable_html(data:dict, result:dict)->bytes:
    source=result.get('method_label',result['engine'])
    reference=result['engine']=='independent-k18-python'
    caution=('This report reproduces the original K18 calculation (Mathcad v2; '
             'source report v1). It is not an independent normative certification.'
             if reference else
             'EXPERIMENTAL PARAMETRIC RESULTS. Separate X/Y checks are not a verified '
             'biaxial N–Mx–My fire-resistance assessment. This report does not certify R90.')
    g=data['geometry'];fire=data['fire'];m=data['material']
    blocks=[]
    for i,v in enumerate(data['variants']):
        results=result['variants'][v['id']]
        schedule=bar_schedule(data,i,result)
        axes=results['axes']
        reinforcement_rows=''.join('<tr><td>'+escape(name)+'</td><td>'+escape(value)+'</td></tr>'
            for name,value in definition_rows(data,i))
        axis_rows=''.join('<tr>'+''.join(f'<td>{escape(val)}</td>' for val in row)+'</tr>'
                for row in [
                    (name.upper(),_fmt(v['N_kN'],2),_fmt(a['M_Ed_kNm'],3),
                     _fmt(a['M_Rd_kNm'],3),_fmt(a['eta'],4),_fmt(a['utilization'],4))
                    for name,a in axes.items()])
        bar_rows=''.join('<tr>'+''.join(f'<td>{escape(str(val))}</td>' for val in row)+'</tr>'
           for row in [(item['Bar'],f"{item['X [mm]']:g}",f"{item['Y [mm]']:g}",
                        f"{item['Ø [mm]']:g}",f"{item['Cover left [mm]']:g}",
                        f"{item['Cover bottom [mm]']:g}",f"{item.get('T [°C]','—')}") for item in schedule])
        blocks.append(f'''<section class="variant">
<h2>Reinforcement variant {escape(v['id'])}</h2>
<p class="detail">{escape(steel_legend(data,i))}; N = {_fmt(v['N_kN'],2)} kN,
Mx = {_fmt(v['M_x_kNm'],2)} kN·m, My = {_fmt(v['M_y_kNm'],2)} kN·m.</p>
<h3>Reinforcement definition</h3>
<table><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>{reinforcement_rows}</tbody></table>
{section_svg(data,i)}
<h3>Cross-section capacity — separate axes</h3>
<table><thead><tr><th>Axis</th><th>N [kN]</th><th>MEd [kN·m]</th><th>MRd [kN·m]</th><th>η</th><th>MEd/MRd</th></tr></thead><tbody>{axis_rows}</tbody></table>
<h3>Reinforcement coordinates and diameters</h3>
<table><thead><tr><th>Bar</th><th>x [mm]</th><th>y [mm]</th><th>Ø [mm]</th><th>Left cover [mm]</th><th>Bottom cover [mm]</th><th>T [°C]</th></tr></thead><tbody>{bar_rows}</tbody></table>
</section>''')
    page=f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Reinforced concrete fire analysis — printable results</title>
<style>
@page{{size:A4;margin:16mm 16mm 18mm}}
*{{box-sizing:border-box}}
body{{max-width:980px;margin:24px auto;padding:0 16px;font:13px/1.5 Arial,Helvetica,sans-serif;color:#18212e;background:white}}
h1{{margin:0 0 6px;font-size:24px}}h2{{border-bottom:1px solid #cbd5e1;margin:22px 0 10px;padding-bottom:6px;font-size:17px}}
h3{{font-size:14px;margin:14px 0 5px}}p{{margin:6px 0 10px}}.subtitle{{color:#475569}}
.warning{{border-left:4px solid #b45309;background:#fffbeb;padding:10px 12px;margin:16px 0;font-weight:600}}
table{{border-collapse:collapse;width:100%;font-size:11px;margin-bottom:12px}}
th,td{{border:1px solid #b8c3cf;padding:5px 6px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}th{{background:#edf2f7}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}}
.cell{{border:1px solid #d6dce4;padding:9px}}.label{{font-size:10px;color:#64748b;text-transform:uppercase}}
.variant{{break-before:page;page-break-before:always}}
.variant:first-of-type{{break-before:auto;page-break-before:auto}}
svg{{max-height:165mm}}
.toolbar{{display:flex;gap:9px;margin:15px 0}}
button{{background:#1d4d71;color:white;border:0;border-radius:5px;padding:9px 15px;cursor:pointer}}
.small{{font-size:10px;color:#64748b}}
@media print{{body{{margin:0;max-width:none;padding:0}}.toolbar{{display:none}}h2,h3,svg,thead{{break-after:avoid}}table{{page-break-inside:auto}}tr{{break-inside:avoid}}}}
</style></head><body>
<div class="toolbar"><button onclick="window.print()">Print / Save as PDF</button></div>
<h1>Reinforced-concrete column — fire calculation</h1>
<p class="subtitle">Calculation output · {date.today().isoformat()} · {escape(source)}</p>
<div class="warning">{escape(caution)}</div>
<div class="grid">
<div class="cell"><div class="label">Section</div><strong>{g['b_m']*1000:g} × {g['h_m']*1000:g} mm</strong></div>
<div class="cell"><div class="label">Length / effective factors</div><strong>{g['length_m']:g} m / μx={data['mechanics']['mu_x']:g}, μy={data['mechanics']['mu_y']:g}</strong></div>
<div class="cell"><div class="label">Fire duration</div><strong>{fire['minutes']:g} min, 4 faces</strong></div>
<div class="cell"><div class="label">Concrete strength</div><strong>{m['f_ck_MPa']:g} MPa</strong></div>
<div class="cell"><div class="label">Reinforcement steel</div><strong>{m['f_y_MPa']:g} MPa</strong></div>
<div class="cell"><div class="label">Calculation</div><strong>{'K18 reproduction' if reference else 'Experimental parametric'}</strong></div>
</div>
{''.join(blocks)}
<p class="small">This print summary is not the original 32-page Word master. For the full Word layout, upload the original reference template within the app.</p>
</body></html>'''
    return page.encode('utf-8')
