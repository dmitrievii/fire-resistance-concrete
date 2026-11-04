"""Single-workspace rectangular reinforced-concrete fire calculator.

Always presents editable parametric inputs, starting from the original K18
example. Solver provenance is selected automatically; it is never a user mode.
The original client Word master is session-uploaded, not published on GitHub.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

import pandas as pd
import streamlit as st

from calculation_engine import ModelError
from app_core import (SCHEMA_PARAMETRIC, SCHEMA_LEGACY, load_example,
                      legacy_to_parametric, validate_json_payload,
                      execute, summary_rows, bars_table, parse_bars_table,
                      with_variant_count, generate_docx, compact_json_bytes, input_fingerprint)
from section_drawing import dimensioned_figure, bar_schedule, steel_legend
from print_report import make_printable_html

st.set_page_config(page_title='RC Fire · Rectangular Section',page_icon='📐',layout='wide')


def num(label,value,key,min_value=None,max_value=None,step=1.0):
    return st.number_input(label,value=float(value),min_value=min_value,
                           max_value=max_value,step=float(step),key=key)


def init():
    if 'draft_input' not in st.session_state:
        original=load_example('k18')
        result=execute(original)
        st.session_state['draft_input']=original
        st.session_state['revision']=0
        st.session_state['last_run']={'inputs':deepcopy(original),'result':result,
                  'fingerprint':input_fingerprint(original)}
        st.session_state['docx']=None


def replace_input(data:dict,calculate:bool=False):
    st.session_state['draft_input']=data
    st.session_state['revision']+=1
    st.session_state['last_run']=None
    st.session_state['docx']=None
    if calculate:
        try:
            result=execute(data)
            st.session_state['last_run']={'inputs':deepcopy(data),'result':result,
                             'fingerprint':input_fingerprint(data)}
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            st.session_state['startup_error']=str(exc)
    st.rerun()


init()
st.title('Reinforced-concrete column — fire analysis')
st.caption('Parametric rectangular section · interactive reinforcement drawing · editable calculation · printable results')

with st.sidebar:
    st.subheader('Project')
    if st.button('Reset to reference K18',use_container_width=True):
        replace_input(load_example('k18'),calculate=True)
    if st.button('Load 720 × 500 mm example',use_container_width=True):
        replace_input(load_example('parametric'),calculate=False)
    uploaded_json=st.file_uploader('Import input JSON',type=['json'])
    if uploaded_json and st.button('Apply JSON',use_container_width=True):
        try:
            raw=json.loads(uploaded_json.getvalue().decode('utf-8'))
            if raw.get('schema')==SCHEMA_LEGACY:
                raw=legacy_to_parametric(raw)
            if raw.get('schema')!=SCHEMA_PARAMETRIC:
                raise ModelError('Only rectangular-section input JSON is supported')
            validate_json_payload(raw)
            replace_input(raw)
        except (ValueError,UnicodeError,TypeError,KeyError,ModelError) as exc:
            st.error(f'Import rejected: {exc}')
    base=st.session_state['draft_input']
    rev=st.session_state['revision']
    count=st.number_input('Number of reinforcement variants',min_value=1,max_value=12,
                          value=len(base['variants']),step=1,key=f'variant_count_{rev}')
    if st.button('Apply variant count',use_container_width=True):
        try:replace_input(with_variant_count(base,int(count)))
        except ModelError as exc:st.error(str(exc))
    st.divider()
    st.caption('The reference report template is not stored in this public repository. Upload it only when generating Word.')

if st.session_state.get('startup_error'):
    st.warning(st.session_state.pop('startup_error'))

edited=deepcopy(base)
left,right=st.columns([1.03,1.25],gap='large')
with left:
    st.subheader('1 · Section and material')
    ca,cb=st.columns(2)
    with ca:
        edited['geometry']['b_m']=num('Width b [mm]',base['geometry']['b_m']*1000,f'b_{rev}',250.,2000.,10.)/1000
        edited['geometry']['h_m']=num('Height h [mm]',base['geometry']['h_m']*1000,f'h_{rev}',250.,2000.,10.)/1000
        edited['geometry']['length_m']=num('Column length [m]',base['geometry']['length_m'],f'length_{rev}',1.,40.,.25)
    with cb:
        edited['material']['f_ck_MPa']=num('Concrete fck [MPa]',base['material']['f_ck_MPa'],f'fck_{rev}',5.,100.,1.)
        edited['material']['f_y_MPa']=num('Steel fy [MPa]',base['material']['f_y_MPa'],f'fy_{rev}',100.,800.,10.)
        edited['material']['E_s_GPa']=num('Steel Es [GPa]',base['material']['E_s_GPa'],f'Es_{rev}',1.,None,10.)
    with st.expander('Additional material / fire parameters'):
        edited['material']['E_cm_GPa']=num('Concrete Ecm [GPa]',base['material']['E_cm_GPa'],f'Ec_{rev}',.1,None,1.)
        edited['fire']['minutes']=num('Fire exposure [min]',base['fire']['minutes'],f'fire_{rev}',1.,240.,15.)
        edited['fire']['a_red_m2_h']=num('Thermal diffusivity [m²/h]',base['fire']['a_red_m2_h'],f'ared_{rev}',.00001,.02,.0001)
        edited['fire']['phi_1']=num('Temperature parameter φ₁',base['fire']['phi_1'],f'phi1_{rev}',0.,2.,.01)
        edited['fire']['phi_2']=num('Temperature parameter φ₂',base['fire']['phi_2'],f'phi2_{rev}',0.,2.,.01)
        edited['fire']['critical_concrete_C']=num('Critical concrete isotherm [°C]',
            base['fire'].get('critical_concrete_C',500),f'critical_{rev}',20.,800.,10.)
    st.caption('Four-sided standard fire is the supported calculation envelope. All bar positions are measured from the left and bottom faces.')

    st.subheader('2 · Loads and effective lengths')
    col1,col2=st.columns(2)
    with col1:edited['mechanics']['mu_x']=num('Effective length factor μx',base['mechanics']['mu_x'],f'mux_{rev}',.05,2.5,.05)
    with col2:edited['mechanics']['mu_y']=num('Effective length factor μy',base['mechanics']['mu_y'],f'muy_{rev}',.05,2.5,.05)
    for i, v in enumerate(edited['variants']):
        with st.expander(f"{v['id']} · Actions",expanded=i==1 or len(edited['variants'])==1):
            a,b,c=st.columns(3)
            with a:v['N_kN']=num('N [kN]',v['N_kN'],f'N_{rev}_{i}',.001,None,10.)
            with b:v['M_x_kNm']=num('Mx [kN·m]',v['M_x_kNm'],f'Mx_{rev}_{i}',None,None,1.)
            with c:v['M_y_kNm']=num('My [kN·m]',v['M_y_kNm'],f'My_{rev}_{i}',None,None,1.)

    st.subheader('3 · Reinforcement layout')
    st.caption('Edit, add or delete individual bars. Diameters and centre coordinates change the geometry in the drawing.')
    for i,v in enumerate(edited['variants']):
        with st.expander(f"{v['id']} · {len(base['variants'][i]['bars'])} bars · {steel_legend(base,i)}",expanded=i==1 or len(edited['variants'])==1):
            df=pd.DataFrame(bars_table(base,i))
            table=st.data_editor(df,num_rows='dynamic',hide_index=True,
                   use_container_width=True,key=f'rebars_{rev}_{i}',
                   column_config={
                      'ID':st.column_config.TextColumn('Bar',required=True),
                      'X [mm]':st.column_config.NumberColumn('X [mm]',required=True,format='%.1f'),
                      'Y [mm]':st.column_config.NumberColumn('Y [mm]',required=True,format='%.1f'),
                      'Diameter [mm]':st.column_config.NumberColumn('Ø [mm]',required=True,format='%.1f')})
            try:v['bars']=parse_bars_table(table.to_dict('records'))
            except ModelError as exc:
                v['bars']=[]
                st.error(str(exc))

with right:
    st.subheader('Live cross-section drawing')
    ids=[v['id'] for v in edited['variants']]
    sel=st.selectbox('Reinforcement variant',options=ids,index=min(1,len(ids)-1),key=f'preview_{rev}')
    selected_index=ids.index(sel)
    opt1,opt2=st.columns(2)
    with opt1:dimensions=st.checkbox('Show dimension chains',value=True,key=f'dim_{rev}')
    with opt2:labels=st.checkbox('Show bar IDs / diameters',value=True,key=f'labels_{rev}')
    try:
        preview_run=st.session_state['last_run']
        # Only use temperatures from a calculation if current draft matches its inputs.
        fingerprint=input_fingerprint(edited)
        same=bool(preview_run and preview_run['fingerprint']==fingerprint)
        chart=dimensioned_figure(edited,selected_index,
               preview_run['result'] if same else None,dimensions,labels)
        st.plotly_chart(chart,use_container_width=True,config={'displaylogo':False,'scrollZoom':True})
        st.caption(f"{steel_legend(edited,selected_index)} · hover over each bar for coordinates, actual diameter, clear cover and computed temperature. Zoom and pan are enabled.")
        schedule=bar_schedule(edited,selected_index,preview_run['result'] if same else None)
        st.dataframe(pd.DataFrame(schedule),hide_index=True,use_container_width=True,height=330)
        if schedule:
            mincover=min(row[key] for row in schedule for key in
                    ('Cover left [mm]','Cover right [mm]','Cover bottom [mm]','Cover top [mm]'))
            st.caption(f'Minimum clear face cover: {mincover:g} mm. Shown for geometry inspection, not code compliance.')
    except (ValueError,KeyError,TypeError,OverflowError) as exc:
        st.error(f'Section preview unavailable: {exc}')

# Drafts are refreshed on every rerun so changing the number of variants keeps edits.
st.session_state['draft_input']=deepcopy(edited)
current_fp=input_fingerprint(edited)
record=st.session_state.get('last_run')
up_to_date=bool(record and record['fingerprint']==current_fp)

st.divider()
actions_col,download_col=st.columns([1,2])
with actions_col:
    if st.button('Calculate section',type='primary',use_container_width=True):
        try:
            result=execute(edited)
            st.session_state['last_run']={'inputs':deepcopy(edited),'result':result,'fingerprint':current_fp}
            st.session_state['docx']=None
            st.rerun()
        except (ModelError,ValueError,KeyError,TypeError,OverflowError) as exc:
            st.session_state['last_run']=None
            st.session_state['docx']=None
            st.error(f'Calculation rejected: {exc}')
with download_col:
    st.download_button('Download editable input JSON',data=compact_json_bytes(edited),
                       file_name='rc_section_input.json',mime='application/json',use_container_width=True)

record=st.session_state.get('last_run')
up_to_date=bool(record and record['fingerprint']==current_fp)
if not up_to_date:
    st.info('The section drawing is live. Press **Calculate section** to refresh results and printable reports after editing inputs.')
else:
    data=record['inputs']; result=record['result']
    reference=result['engine']=='independent-k18-python'
    st.subheader('4 · Calculated results')
    if reference:
        st.info('Reference K18 geometry detected. Values reproduced from the original calculation method (Mathcad v2 and report v1).')
    else:
        st.warning('Modified geometry, reinforcement or conditions: experimental fiber solver used. Results are **not** a validated biaxial fire-resistance assessment.')
    st.dataframe(pd.DataFrame(summary_rows(result)),hide_index=True,use_container_width=True)
    c1,c2=st.columns(2)
    with c1:
        st.download_button('Download results JSON',data=compact_json_bytes(result),
                           file_name='rc_calculation_results.json',mime='application/json',use_container_width=True)
    with c2:
        st.download_button('Print / Save as PDF (HTML)',data=make_printable_html(data,result),
                  file_name='RC_Fire_Printable_Report.html',mime='text/html',use_container_width=True,
                  help='Open the HTML in a browser and use its Print / Save as PDF command.')
    st.caption('The printable HTML includes actual section dimensions, reinforcement layout, bar schedule and computed values. No Word template is required.')

    st.subheader('5 · Original-layout Word report')
    st.caption('To retain the engineering frame and stamp, upload the original `Пример.docx` for this session. It is not stored in GitHub.')
    template=st.file_uploader('Original Word master',type=['docx'],key='template_upload')
    if template is not None:
        content=template.getvalue()
        signature=sha256(compact_json_bytes(data)+content).hexdigest()
        if st.button('Generate Word report',type='primary'):
            try:
                docx,audit=generate_docx(data,result,content)
                st.session_state['docx']={'signature':signature,'content':docx,
                    'audit':audit,'name':'K18_Reference_Report.docx' if reference else 'RC_Parametric_Diagnostic.docx'}
            except (ModelError,ValueError,KeyError,TypeError,AssertionError,RuntimeError) as exc:
                st.session_state['docx']=None
                st.error(f'Report generation rejected: {exc}')
        docx_record=st.session_state.get('docx')
        if docx_record and docx_record['signature']==signature:
            st.download_button('Download DOCX',data=docx_record['content'],
                    file_name=docx_record['name'],
                    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            with st.expander('Report audit'):
                st.json(docx_record['audit'])
        if not reference:
            st.caption('The report for altered layouts is a separate diagnostic document. The initial 32-page normative prose is not suitable for all geometries.')

st.divider()
st.caption('One parameterized interface. Exact K18 data are displayed by default; modified physical models are labelled experimental. No normative R90 certification is implied.')
