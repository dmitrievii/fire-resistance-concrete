"""Streamlit engineering reinforcement editor (perimeter and custom layouts)."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from calculation_engine import ModelError
from app_core import bars_table, parse_bars_table
from reinforcement_layout import active_definition, infer_perimeter, generate_perimeter
from section_drawing import steel_legend


def render_reinforcement(edited:dict, base:dict, rev:int, num) -> list[str]:
    layout_errors=[]
    st.subheader('3 · Reinforcement layout')
    st.caption('Specify perimeter bars by diameter, counts and dimensions. The full coordinate list is generated automatically; individual bars remain editable under Custom coordinates.')
    b_mm=edited['geometry']['b_m']*1000
    h_mm=edited['geometry']['h_m']*1000
    for i,v in enumerate(edited['variants']):
        with st.expander(f"{v['id']} · {len(base['variants'][i]['bars'])} bars · {steel_legend(base,i)}",expanded=i==1 or len(edited['variants'])==1):
            original_spec=active_definition(base,i)
            inferred=infer_perimeter(base['geometry']['b_m']*1000,
                                     base['geometry']['h_m']*1000,base['variants'][i]['bars'])
            spec=(original_spec if original_spec['mode']=='perimeter' else (inferred or {
                'mode':'perimeter','basis':'edges','symmetric':True,'nx':3,'ny':3,
                'diameter_mm':25,'left_mm':50,'right_mm':50,'bottom_mm':50,'top_mm':50,
                'spacing_x_mm':250,'spacing_y_mm':250}))
            kind=st.radio('Reinforcement input',('Perimeter layout','Custom coordinates'),
                index=0 if original_spec['mode']=='perimeter' else 1,
                horizontal=True,key=f'layout_type_{rev}_{i}')
            if kind=='Perimeter layout':
                c1,c2,c3=st.columns(3)
                with c1:
                    phi=num('Bar diameter Ø [mm]',spec['diameter_mm'],f'phi_{rev}_{i}',6.,50.,1.)
                with c2:
                    nx=st.number_input('Bars along x (nx)',min_value=2,max_value=33,
                            value=int(spec['nx']),step=1,key=f'nx_{rev}_{i}')
                with c3:
                    ny=st.number_input('Bars along y (ny)',min_value=2,max_value=33,
                            value=int(spec['ny']),step=1,key=f'ny_{rev}_{i}')
                symmetric=st.checkbox('Symmetric edge distances',value=bool(spec['symmetric']),
                                      key=f'symmetric_{rev}_{i}')
                basis=st.radio('Dimension input',('Edge-to-bar-centre distances','Centre-to-centre spacing'),
                              horizontal=True,index=0 if spec.get('basis','edges')=='edges' else 1,
                              key=f'basis_{rev}_{i}')
                definition={'mode':'perimeter','basis':'edges' if basis.startswith('Edge') else 'spacing',
                           'symmetric':symmetric,'nx':nx,'ny':ny,'diameter_mm':phi}
                if definition['basis']=='edges':
                    ca,cb=st.columns(2)
                    with ca:
                        definition['left_mm']=num('Left edge → bar centre [mm]',spec['left_mm'],
                                                  f'left_{rev}_{i}',0.,None,5.)
                        definition['bottom_mm']=num('Bottom edge → bar centre [mm]',spec['bottom_mm'],
                                                    f'bottom_{rev}_{i}',0.,None,5.)
                    if not symmetric:
                        with cb:
                            definition['right_mm']=num('Right edge → bar centre [mm]',spec['right_mm'],
                                                       f'right_{rev}_{i}',0.,None,5.)
                            definition['top_mm']=num('Top edge → bar centre [mm]',spec['top_mm'],
                                                     f'top_{rev}_{i}',0.,None,5.)
                    else:
                        definition['right_mm']=definition['left_mm']
                        definition['top_mm']=definition['bottom_mm']
                else:
                    ca,cb=st.columns(2)
                    with ca:
                        definition['spacing_x_mm']=num('Bar spacing sx [mm]',spec['spacing_x_mm'],
                                                       f'sx_{rev}_{i}',0.,None,5.)
                    with cb:
                        definition['spacing_y_mm']=num('Bar spacing sy [mm]',spec['spacing_y_mm'],
                                                       f'sy_{rev}_{i}',0.,None,5.)
                    if not symmetric:
                        ca,cb=st.columns(2)
                        with ca: definition['left_mm']=num('Left edge → first centre [mm]',
                                        spec['left_mm'],f'left_sp_{rev}_{i}',0.,None,5.)
                        with cb: definition['bottom_mm']=num('Bottom edge → first centre [mm]',
                                        spec['bottom_mm'],f'bottom_sp_{rev}_{i}',0.,None,5.)
                try:
                    v['bars'],p=generate_perimeter(b_mm,h_mm,definition)
                    # Store the complete engineering input contract, not transient metrics.
                    v['reinforcement']={k:p[k] for k in (
                        'mode','basis','symmetric','nx','ny','diameter_mm',
                        'left_mm','right_mm','bottom_mm','top_mm',
                        'spacing_x_mm','spacing_y_mm')}
                    st.caption(f"**{p['bar_count']} bars** · As = {p['area_mm2']:.1f} mm² · "
                               f"sx = {p['spacing_x_mm']:.1f} mm · sy = {p['spacing_y_mm']:.1f} mm")
                    st.caption(f"Bar-centre distances L/R/B/T: {p['left_mm']:.1f} / "
                               f"{p['right_mm']:.1f} / {p['bottom_mm']:.1f} / "
                               f"{p['top_mm']:.1f} mm. Clear cover is "
                               f"{p['clear_cover_left_mm']:.1f} / {p['clear_cover_right_mm']:.1f} / "
                               f"{p['clear_cover_bottom_mm']:.1f} / {p['clear_cover_top_mm']:.1f} mm.")
                except ModelError as exc:
                    layout_errors.append(f"{v['id']}: {exc}")
                    v['bars']=base['variants'][i]['bars']
                    v['reinforcement']=definition
                    st.error(f'Invalid reinforcement layout: {exc}. Calculation disabled until fixed.')
            else:
                st.caption('Advanced input: edit any individual bar ID, centre x/y [mm] and diameter Ø [mm].')
                df=pd.DataFrame(bars_table(base,i))
                table=st.data_editor(df,num_rows='dynamic',hide_index=True,
                       use_container_width=True,key=f'rebars_{rev}_{i}',
                       column_config={
                          'ID':st.column_config.TextColumn('Bar',required=True),
                          'X [mm]':st.column_config.NumberColumn('X [mm]',required=True,format='%.1f'),
                          'Y [mm]':st.column_config.NumberColumn('Y [mm]',required=True,format='%.1f'),
                          'Diameter [mm]':st.column_config.NumberColumn('Ø [mm]',required=True,format='%.1f')})
                v['reinforcement']={'mode':'custom'}
                try:v['bars']=parse_bars_table(table.to_dict('records'))
                except ModelError as exc:
                    layout_errors.append(f"{v['id']}: {exc}")
                    v['bars']=[]
                    st.error(str(exc))

    return layout_errors
