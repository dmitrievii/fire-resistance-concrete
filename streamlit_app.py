"""Streamlit UI for K18 and experimental rectangular RC fire calculations.

Engineering caution: the generalized model is NOT certified for Belarusian
fire-resistance design. The original Word master is never stored in this repo.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import pandas as pd
import streamlit as st

from calculation_engine import ModelError
from app_core import (load_example, execute, summary_rows, bars_table,
                      parse_bars_table, with_variant_count, generate_docx,
                      compact_json_bytes, SCHEMA_LEGACY, SCHEMA_PARAMETRIC)

st.set_page_config(page_title='RC Fire Report · K18', page_icon='🏗️', layout='wide')


def num(label, value, key, min_value=None, max_value=None, step=1.0):
    return st.number_input(label, value=float(value), min_value=min_value,
                           max_value=max_value, step=float(step), key=key)


def graphic(data, variant):
    b, h = data['geometry']['b_m']*1000, data['geometry']['h_m']*1000
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.add_patch(Rectangle((0, 0), b, h, fill=False, lw=1.6))
    for bar in variant['bars']:
        ax.add_patch(Circle((bar['x_m']*1000, bar['y_m']*1000),
                            bar['diameter_mm']/2, color='#355D84'))
        ax.annotate(str(bar['id']), (bar['x_m']*1000, bar['y_m']*1000),
                    xytext=(4, 4), textcoords='offset points', fontsize=8)
    ax.set_xlim(-.1*b, 1.1*b); ax.set_ylim(-.12*h, 1.12*h)
    ax.set_aspect('equal');ax.set_xlabel('x [mm]');ax.set_ylabel('y [mm]')
    ax.grid(alpha=.15)
    fig.tight_layout()
    return fig


st.title('Reinforced-concrete column · Fire report generator')
st.caption('R0.4 web MVP — Python calculations and DOCX report generation')
st.warning('The generalized model is experimental. Its X/Y checks are not a normative N–Mx–My interaction verification. Do not use its report as evidence of R90 compliance.', icon='⚠️')

mode = st.sidebar.radio('Calculation model',
        ['Reference K18 (Mathcad reproduction)', 'Parametric rectangular section'], index=0)
mode_key = 'legacy' if mode.startswith('Reference') else 'parametric'
if st.session_state.get('current_mode') != mode_key:
    st.session_state['current_mode'] = mode_key
    st.session_state['input_data'] = load_example(mode_key)
    st.session_state['revision'] = st.session_state.get('revision', 0) + 1
    st.session_state['last_run'] = None

st.sidebar.subheader('Input / export')
uploaded_json = st.sidebar.file_uploader('Import calculation JSON', type='json', key=f'upload_{mode_key}')
if uploaded_json and st.sidebar.button('Apply uploaded JSON'):
    try:
        doc = json.loads(uploaded_json.getvalue().decode('utf-8'))
        if doc.get('schema') != (SCHEMA_LEGACY if mode_key=='legacy' else SCHEMA_PARAMETRIC):
            raise ModelError('Imported schema does not match the selected mode')
        from app_core import validate_json_payload
        validate_json_payload(doc)
        st.session_state['input_data'] = doc
        st.session_state['revision'] += 1
        st.session_state['last_run'] = None
        st.rerun()
    except (ValueError,UnicodeError,ModelError,TypeError) as exc:
        st.sidebar.error(f'Import rejected: {exc}')

base = st.session_state['input_data']
rev = st.session_state['revision']

if mode_key == 'parametric':
    with st.sidebar:
        new_count = st.number_input('Number of variants',min_value=1,max_value=12,
                                    value=len(base['variants']),step=1,key=f'count_{rev}')
        if st.button('Change variant count'):
            try:
                st.session_state['input_data'] = with_variant_count(base, int(new_count))
                st.session_state['revision'] += 1
                st.session_state['last_run'] = None
                st.rerun()
            except ModelError as exc:st.error(str(exc))

st.sidebar.info('Only 4-sided standard-fire exposure is supported. The original Word template is uploaded per session and is never included in the public source files.')

with st.form(f'calculator_form_{mode_key}_{rev}'):
    geometry, actions, reinf = st.tabs(['Geometry, materials & fire', 'Actions & stability', 'Reinforcement'])
    edited = deepcopy(base)
    with geometry:
        c1,c2,c3 = st.columns(3)
        with c1:
            edited['geometry']['b_m'] = num('Width b [mm]',base['geometry']['b_m']*1000,f'b_{rev}',250.,2000.,10.)/1000
            edited['geometry']['h_m'] = num('Depth h [mm]',base['geometry']['h_m']*1000,f'h_{rev}',250.,2000.,10.)/1000
            edited['geometry']['length_m'] = num('Column length [m]',base['geometry']['length_m'],f'l_{rev}',1.,40.,.25)
        with c2:
            for field,label in [('f_ck_MPa','Concrete fck [MPa]'),('E_cm_GPa','Concrete Ecm [GPa]'),('f_y_MPa','Steel fy [MPa]'),('E_s_GPa','Steel Es [GPa]')]:
                edited['material'][field] = num(label,base['material'][field],f'{field}_{rev}',0.1,None,1.)
        with c3:
            edited['fire']['minutes'] = num('Fire duration [min]',base['fire']['minutes'],f'fire_{rev}',1.,240.,15.)
            edited['fire']['a_red_m2_h'] = num('Thermal diffusivity [m²/h]',base['fire']['a_red_m2_h'],f'ared_{rev}',.00001,.02,.0001)
            for field in ('phi_1','phi_2'):
                edited['fire'][field] = num(field.replace('_',' '),base['fire'][field],f'{field}_{rev}',0.,2.,.01)
            if mode_key=='parametric':
                edited['fire']['critical_concrete_C']=num('Concrete isotherm [°C]',base['fire'].get('critical_concrete_C',500),f'tcr_{rev}',20.,800.,10.)
            st.caption('Fire-exposed faces are fixed to all four sides in this release.')
    with actions:
        c1,c2=st.columns(2)
        with c1:
            for field,label in [('mu_x','Effective length factor μx'),('mu_y','Effective length factor μy')]:
                edited['mechanics'][field]=num(label,base['mechanics'][field],f'{field}_{rev}',.05,2.5,.05)
        with c2:
            if mode_key=='legacy':
                st.info('The original K18 report contains fixed geometry, steel layout and R90 wording. Non-representable cases are rejected by the engine.')
            else:
                st.info('The numeric fiber-section model checks X and Y separately. Its results are diagnostics only.')
        for i,variant in enumerate(edited['variants']):
            with st.expander(f"Actions — {variant['id']}", expanded=i==0):
                col1,col2,col3=st.columns(3)
                with col1:variant['N_kN']=num('Axial N [kN]',variant['N_kN'],f'N_{rev}_{i}',.001,None,10.)
                with col2:variant['M_x_kNm']=num('Mx [kNm]',variant['M_x_kNm'],f'Mx_{rev}_{i}',None,None,1.)
                with col3:variant['M_y_kNm']=num('My [kNm]',variant['M_y_kNm'],f'My_{rev}_{i}',None,None,1.)
    with reinf:
        if mode_key=='legacy':
            st.info('Reference layout: three bars per face, Ø20 and Ø25 mm. To position individual bars, choose parametric mode.')
            for i,v in enumerate(edited['variants']):
                v['bar_diameter_mm']=num(f"{v['id']} bar diameter [mm]",v['bar_diameter_mm'],f'bar_d_{rev}_{i}',6.,50.,1.)
        else:
            for i,v in enumerate(edited['variants']):
                st.markdown(f"**Variant {v['id']}** — edit/add/delete rows; coordinates are measured from the left/bottom face.")
                df=pd.DataFrame(bars_table(base,i))
                result_df=st.data_editor(df, num_rows='dynamic',hide_index=True,
                    key=f'bars_{rev}_{i}',use_container_width=True,
                    column_config={
                      'ID':st.column_config.TextColumn('ID',required=True),
                      'X [mm]':st.column_config.NumberColumn('X [mm]',required=True,format='%.2f'),
                      'Y [mm]':st.column_config.NumberColumn('Y [mm]',required=True,format='%.2f'),
                      'Diameter [mm]':st.column_config.NumberColumn('Diameter [mm]',required=True,format='%.1f')})
                try:v['bars']=parse_bars_table(result_df.to_dict('records'))
                except ModelError as exc:
                    st.error(str(exc));v['bars']=[]
    submitted=st.form_submit_button('Calculate',type='primary',use_container_width=True)

if submitted:
    try:
        result = execute(edited)
        st.session_state['last_run'] = {'inputs':edited,'result':result}
        st.session_state['input_data'] = edited
    except (ModelError,ValueError,KeyError,TypeError,OverflowError) as exc:
        st.session_state['last_run']=None
        st.error(f'Calculation rejected: {exc}')

record=st.session_state.get('last_run')
if record:
    st.caption('Displayed results correspond to the last successful Calculate action. Recalculate after editing inputs.')
    used=record['inputs'];result=record['result']
    st.subheader('Calculation results')
    st.dataframe(pd.DataFrame(summary_rows(result)),hide_index=True,use_container_width=True)
    if used['schema']==SCHEMA_PARAMETRIC:
        st.info('The reported single-axis passes are NOT equivalent to a verified biaxial fire-resistance check.')
        a,b=st.columns(2)
        with a:
            figure=graphic(used,used['variants'][0]);st.pyplot(figure,clear_figure=True);plt.close(figure)
        with b:
            bars=pd.DataFrame(result['variants'][used['variants'][0]['id']]['bars'])
            st.dataframe(bars[['id','x_m','y_m','diameter_mm','temperature_C','k','beta']],use_container_width=True,hide_index=True)
    else:
        st.caption('Reference mode reproduces the input worksheet. Do not assume independent normative validation.')
    c1,c2=st.columns(2)
    with c1:st.download_button('Download calculation JSON',data=compact_json_bytes(result),file_name='calculation_results.json',mime='application/json',use_container_width=True)
    with c2:st.download_button('Download editable input JSON',data=compact_json_bytes(used),file_name='input.json',mime='application/json',use_container_width=True)

    st.subheader('Generate Word report')
    st.caption('Upload the exact original K18 Пример.docx. It is only used inside this calculation session and is not written to the repository.')
    template_upload=st.file_uploader('Original reference DOCX',type=['docx'],key=f'template_{mode_key}')
    if template_upload:
        template_bytes=template_upload.getvalue()
        digest=sha256(compact_json_bytes(used)+template_bytes).hexdigest()
        if st.button('Generate DOCX report',type='primary'):
            try:
                report_bytes,audit=generate_docx(used,result,template_bytes)
                st.session_state['docx']={'digest':digest,'bytes':report_bytes,'audit':audit,
                   'file_name':'K18_Reference_Report.docx' if mode_key=='legacy' else 'RC_Parametric_Diagnostic.docx'}
            except (ModelError,ValueError,KeyError,TypeError,RuntimeError,AssertionError) as exc:
                st.session_state['docx']=None
                st.error(f'Report rejected: {exc}')
        report=st.session_state.get('docx')
        if report and report['digest']==digest:
            st.download_button('Download DOCX',data=report['bytes'],file_name=report['file_name'],
                 mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            with st.expander('Report audit'):
                st.json(report['audit'])

st.divider()
st.caption('K18 / R0.4 Streamlit prototype. Original project documents, Mathcad worksheets and third-party standards must not be committed to a public repository without authorization.')
