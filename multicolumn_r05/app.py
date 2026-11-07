"""Streamlit R0.5: multicolumn RC fire diagnostic and Word/PDF reports.
Run: streamlit run app.py
"""
from __future__ import annotations
import io
import json
import math
import shutil

import pandas as pd
import streamlit as st

from multicolumn_r05.project_model import (new_project,set_count,update_column,update_section,
    add_section,remove_section,replace_bars,reset_auto_bars,get_column,
    overview_rows,section_overview_rows,update_from_overview,update_from_section_overview,
    export_json,load_json,load_state,CONCRETE,update_material_spec,update_thermal_spec)
from multicolumn_r05.project_calculator import evaluate_project
from multicolumn_r05.project_reports import make_exports
from multicolumn_r05.r056_ui import render_spalling_inputs, render_r056_results, render_r056_overview
from multicolumn_r05.section_preview import make_section_figure
from rc_fire.materials.ui import render_material_inputs
from rc_fire.thermal.ui import render_thermal_inputs, render_thermal_results, render_thermal_overview
from rc_fire.mechanics.ui import render_mechanics_results, render_mechanics_overview

st.set_page_config(page_title='Огнестойкость ЖБ колонн',page_icon='🏗️',layout='wide')

if 'project' not in st.session_state:
    st.session_state.project=new_project(1)
if 'exports' not in st.session_state:
    st.session_state.exports=None

project=st.session_state.project


def change_project():
    st.session_state.exports=None


def safe_change(fn,*args,**kwargs):
    try:
        fn(*args,**kwargs)
        change_project()
        st.rerun()
    except (ValueError,KeyError,TypeError) as exc:
        st.error(f'Изменение не принято: {exc}')


def editor_records(df):
    records=df.to_dict('records')
    for row in records:
        for k,v in row.items():
            if v is pd.NA or (isinstance(v,float) and pd.isna(v)):
                row[k]=None
    return records


def show_overview():
    st.title('Обзор проекта')
    st.caption('Единая редактируемая таблица: изменения автоматически попадают в карточки колонн и результаты. Результаты — диагностические, не подтверждение R90.')
    top=st.columns([2,2,3])
    with top[0]:
        n=st.number_input('Количество колонн',min_value=1,max_value=30,value=len(project['columns']),step=1,key=f"count_{project['revision']}")
        if int(n)!=len(project['columns']):safe_change(set_count,project,int(n))
    with top[1]:
        st.metric('В проекте',len(project['columns']))
    with top[2]:
        st.text_input('Название проекта',value=project.get('title',''),key=f"project_title_{project['revision']}",on_change=None)
        title=st.session_state[f"project_title_{project['revision']}"]
        if title!=project.get('title'):
            project['title']=title;project['revision']+=1;change_project();st.rerun()

    st.subheader('Параметры конструкций')
    source=pd.DataFrame(overview_rows(project))
    output=st.data_editor(source,hide_index=True,use_container_width=True,num_rows='fixed',
        disabled=['ID','Арматура'],key=f"overview_params_v{project['revision']}",
        column_config={'Бетон':st.column_config.SelectboxColumn(options=list(CONCRETE)),
                       'Колонна':st.column_config.TextColumn(required=True),
                       'b, мм':st.column_config.NumberColumn(min_value=250,max_value=2000,step=10),
                       'h, мм':st.column_config.NumberColumn(min_value=250,max_value=2000,step=10),
                       'L, м':st.column_config.NumberColumn(min_value=1.0,max_value=40.0,step=.5),
                       'c, мм':st.column_config.NumberColumn(min_value=5,max_value=150,step=5),
                       'Ø, мм':st.column_config.NumberColumn(min_value=6,max_value=50,step=2)})
    if not source.equals(output):
        try:
            changes=update_from_overview(project,editor_records(output))
            if changes:change_project();st.rerun()
        except (ValueError,TypeError,KeyError) as exc:st.error(f'Недопустимые данные: {exc}')
    st.subheader('Нагрузки по расчётным сечениям')
    st.caption('Пустая ячейка означает отсутствие данных; N = 0 не подставляется автоматически. Для расчёта нужны N>0, Mx и My в каждом сечении.')
    loads=pd.DataFrame(section_overview_rows(project))
    for field in ('N, кН','Mx, кН·м','My, кН·м'):
        loads[field]=pd.to_numeric(loads[field],errors='coerce')
    loads_result=st.data_editor(loads,hide_index=True,use_container_width=True,num_rows='fixed',
        disabled=['ID','Сечение ID','Колонна','Сечение'],key=f"overview_loads_v{project['revision']}",
        column_config={'N, кН':st.column_config.NumberColumn(format='%.2f'),
                       'Mx, кН·м':st.column_config.NumberColumn(format='%.2f'),
                       'My, кН·м':st.column_config.NumberColumn(format='%.2f')})
    if not loads.equals(loads_result):
        try:
            changes=update_from_section_overview(project,editor_records(loads_result))
            if changes:change_project();st.rerun()
        except (ValueError,TypeError,KeyError) as exc:st.error(f'Некорректные усилия: {exc}')
    st.subheader('Результаты')
    resultrows=[]
    for c in project['columns']:
        result=calculations[c['id']]
        w=result['worst']
        resultrows.append({'Колонна':c['name'],'Сечений':len(c['sections']),
            'Статус':{'pending':'Нет нагрузок','calculated':'Рассчитано','partial':'Частично',
                      'invalid':'Ошибка ввода','error':'Ошибка расчёта'}.get(result['status'],result['status']),
            'Критическое сечение*':w['section_id'] if w else '—',
            'Ось*':w['axis'].upper() if w else '—',
            'max u*':round(w['u'],3) if w else None})
    st.dataframe(pd.DataFrame(resultrows),hide_index=True,use_container_width=True)
    render_thermal_overview(st,project,calculations)
    render_mechanics_overview(st,project,calculations)
    render_r056_overview(st,project,calculations)
    st.caption('* Условная диагностическая величина max(MEd/MRd) по двум независимым плоскостям и рассчитанным сечениям. Не выполняет нормативную двухосную проверку.')
    if any(x['issues'] for x in calculations.values()):
        with st.expander('Ошибки и предупреждения'):
            for c in project['columns']:
                for msg in calculations[c['id']]['issues']:
                    st.warning(c['name']+': '+str(msg))

    st.divider()
    st.subheader('Сохранение проекта и отчёты')
    buttons=st.columns([1,1,1])
    with buttons[0]:
        st.download_button('Скачать проект JSON',data=export_json(project),file_name='K18_project.json',
            mime='application/json',use_container_width=True)
    with buttons[1]:
        uploaded=st.file_uploader('Открыть проект JSON',type=['json'],label_visibility='collapsed')
        if uploaded is not None and st.button('Загрузить проект',use_container_width=True):
            try:
                st.session_state.project=load_json(uploaded.getvalue())
                st.session_state.exports=None
                st.rerun()
            except Exception as exc:st.error('Загрузка отклонена: '+str(exc))
    with buttons[2]:
        st.caption('Экспорт включает сводный отчёт, отдельные документы и все исходные данные.')
        if st.button('Новый проект (сброс текущих данных)',key='r065_new_project'):
            st.session_state.project=new_project(len(project['columns']))
            st.session_state.exports=None
            st.rerun()
    can_pdf=shutil.which('libreoffice') is not None or shutil.which('soffice') is not None
    want_pdf=st.checkbox('Создавать также PDF',value=can_pdf,disabled=not can_pdf)
    if not can_pdf:st.info('LibreOffice не установлен; DOCX формируется, PDF доступен после установки LibreOffice.')
    if st.button('Сформировать все отчёты',type='primary'):
        with st.spinner('Генерация DOCX'+('/PDF' if want_pdf else '')+' по всем колоннам'):
            try:
                st.session_state.exports=make_exports(project,calculations,pdf=want_pdf)
                st.success('Отчёты сформированы. Незаполненные нагрузки отражены как черновики.')
            except Exception as exc:
                st.session_state.exports=None
                st.error('Генерация отчётов: '+str(exc))
    if st.session_state.exports:
        st.download_button('Скачать общий отчёт и индивидуальные отчёты (ZIP)',
             data=st.session_state.exports,file_name='K18_R05_reports.zip',
             mime='application/zip',type='primary')


def section_editor(c):
    st.subheader('Расчётные сечения')
    st.caption('По умолчанию одно сечение в центре z=L/2. '
               'Можно добавить любое количество сечений, в том числе на концах z=0 и z=L. '
               'N, Mx и My задаются независимо для каждого сечения.')
    records=pd.DataFrame([{'ID':s['id'],'Сечение':s['name'],'z, м':s['z_m'],
             'N, кН':s['N_kN'],'Mx, кН·м':s['Mx_kNm'],'My, кН·м':s['My_kNm']} for s in c['sections']])
    for field in ('N, кН','Mx, кН·м','My, кН·м'):
        records[field]=pd.to_numeric(records[field],errors='coerce')
    edited=st.data_editor(records,hide_index=True,use_container_width=True,num_rows='fixed',
        disabled=['ID'],key=f"{c['id']}_section_v{project['revision']}")
    if not records.equals(edited):
        try:
            for row in editor_records(edited):
                s=next(t for t in c['sections'] if t['id']==row['ID'])
                fields={}
                for ek,field in [('Сечение','name'),('z, м','z_m'),('N, кН','N_kN'),('Mx, кН·м','Mx_kNm'),('My, кН·м','My_kNm')]:
                    if row[ek]!=s.get(field):fields[field]=row[ek]
                if fields:update_section(project,c['id'],s['id'],fields)
            change_project();st.rerun()
        except Exception as exc:st.error(str(exc))
    a,b=st.columns(2)
    with a:
        if st.button('Добавить сечение',key=f"{c['id']}_add"):
            safe_change(add_section,project,c['id'])
    with b:
        extra=c['sections'] if len(c['sections'])>1 else []
        if extra:
            sid=st.selectbox('Удалить сечение',options=[s['id'] for s in extra],
                             format_func=lambda v:next(x['name'] for x in extra if x['id']==v))
            if st.button('Удалить выбранное',key=f"{c['id']}_remove"):
                safe_change(remove_section,project,c['id'],sid)


def column_page(cid):
    c=get_column(project,cid)
    st.title(f"Колонна {c['name']}")
    st.caption('Прямоугольное железобетонное сечение; защитный слой до наружной поверхности хомута.')
    groups=[('Геометрия',[('Ширина b, мм','b_mm'),('Высота h, мм','h_mm'),('Длина L, м','length_m'),
                          ('Защитный слой, мм','cover_mm'),('Диаметр хомута, мм','stirrup_mm')]),
           ('Армирование и материалы',[('Диаметр продольной арматуры, мм','bar_diameter_mm'),
                      ('μx','mu_x'),('μy','mu_y'),('Пожар, мин','fire_minutes')])]
    for group,fields in groups:
        st.subheader(group)
        cols=st.columns(3)
        for i,(title,key) in enumerate(fields):
            with cols[i%3]:
                old=float(c[key]);v=st.number_input(title,value=old,
                      min_value=0.0,step=1.0 if key not in ('length_m','mu_x','mu_y') else .1,
                      key=f"field_{cid}_{key}_v{project['revision']}")
                if abs(v-old)>1e-9:safe_change(update_column,project,cid,{key:v})
    mat=st.columns(2)
    with mat[0]:
        typ=st.selectbox('Класс бетона',options=list(CONCRETE),
                index=list(CONCRETE).index(c['concrete']),key=f"{cid}_concrete_v{project['revision']}")
        if typ!=c['concrete']:safe_change(update_column,project,cid,{'concrete':typ})
    with mat[1]:
        st.text_input('Марка арматуры (фиксирована для R0.5)',value=c['steel_grade'],disabled=True)
        st.caption('Температурные коэффициенты ядра относятся к S500.')
    render_material_inputs(st,project,c,safe_change,update_material_spec)
    render_thermal_inputs(st,project,c,safe_change,update_thermal_spec)
    render_spalling_inputs(st,project,c,safe_change)
    st.subheader('Схема арматуры')
    drawing_left,drawing_right=st.columns(2)
    with drawing_left:
        show_dimensions=st.checkbox('Показывать размерные цепочки',
            value=True,key=f'{cid}_drawing_dimensions')
    with drawing_right:
        show_labels=st.checkbox('Номера и диаметры стержней',
            value=True,key=f'{cid}_drawing_labels')
    section_figure=make_section_figure(c,calculations.get(cid),
        show_dimensions=show_dimensions,show_ids=show_labels)
    st.plotly_chart(section_figure,use_container_width=True,
        key=f'{cid}_interactive_section')
    st.caption('Масштабная интерактивная схема: окружности соответствуют реальным диаметрам; '
               'при наведении показаны координаты, расстояния до граней и температуры '
               '(если расчёт выполнен). Изменения в таблице или обзоре сразу обновляют схему.')
    st.caption('В автоматическом режиме 8 стержней располагаются по периметру. При ручном вводе координаты индивидуальны и сохраняются при изменении размеров сечения.')
    st.write('Режим:', 'автоматическое расположение' if c['bar_mode']=='perimeter8' else 'ручные координаты')
    bars=pd.DataFrame(c['bars'])
    edited=st.data_editor(bars,hide_index=True,use_container_width=True,
            num_rows='dynamic',key=f"{cid}_bars_v{project['revision']}")
    if not bars.equals(edited):
        try:
            safe_change(replace_bars,project,cid,editor_records(edited))
        except Exception as exc:st.error('Арматура: '+str(exc))
    if st.button('Восстановить автоматическую схему 8 стержней',key=f"{cid}_resetbars"):
        safe_change(reset_auto_bars,project,cid)
    section_editor(c)
    st.subheader('Результаты расчёта')
    calculation=calculations[cid]
    loads=calculation.get('load_summary') or {}
    states=calculation.get('section_statuses',{})
    ready=loads.get('ready',sum(v=='ready' for v in states.values()))
    total=loads.get('total',len(c.get('sections',[])))
    if calculation['status']=='pending':
        if ready:
            msg=f'Усилия переданы ({ready}/{total} сечений заполнено), но расчёт не выполнен: см. ограничения ниже.'
        elif any(v=='incomplete' for v in states.values()):
            msg='Усилия введены не полностью: задайте N, Mx и My. Нулевые моменты допустимы.'
        elif any(v=='invalid' for v in states.values()):
            msg='Часть введённых усилий некорректна; расчёт не запущен.'
        else:
            msg='Усилия ещё не заданы: расчёт не выполнялся.'
    else:
        msg={'partial':f'Рассчитано {ready}/{total} сечений; оставшиеся требуют заполнения.',
             'calculated':f'Усилия переданы, рассчитано {ready}/{total} сечений (только диагностика).',
             'error':'Нагрузки проверены, но вычисление завершилось ошибкой.',
             'invalid':'Есть некорректные исходные данные.'}.get(calculation['status'],calculation['status'])
    st.info(msg)
    for msg in calculation['issues']:st.warning(msg)
    if calculation['results']:
        results=[]
        for s in c['sections']:
            res=calculation['results'].get(s['id'])
            if res:
                for axis,a in res['axes'].items():
                    results.append({'Сечение':s['name'],'Ось':axis.upper(),'N, кН':res['N_kN'],
                                    'Ncr, кН':a['N_cr_kN'],'η':a['eta'],
                                    'MEd, кН·м':a['M_Ed_kNm'],'MRd, кН·м':a['M_Rd_kNm'],
                                    'u':a['utilization']})
        st.dataframe(pd.DataFrame(results),hide_index=True,use_container_width=True)
        w=calculation['worst']
        if w:st.caption(f"Наибольший диагностический u = {w['u']:.3f}; сечение {w['section_id']}, ось {w['axis'].upper()}.")
    render_thermal_results(st,c,calculation)
    render_mechanics_results(st,c,calculation)
    # R064D_REPOSITORY_HOOK: diagnostic-only opt-in, no default solve.
    from rc_fire.integration.ui import render_member_evidence
    render_member_evidence(st,c,calculation)
    render_r056_results(st,calculation)
    st.caption('Численное совместное равновесие N–Mx–My и критерий F (при наличии данных) '
               'рассчитываются в R0.5.6. Это ещё не независимое нормативное подтверждение R90.')

with st.sidebar:
    st.header('ЖБ колонны')
    choices=['Обзор проекта']+[c['id'] for c in project['columns']]
    selected=st.radio('Разделы',choices,format_func=lambda x:'Обзор проекта' if x=='Обзор проекта' else get_column(project,x)['name'])
    st.divider()
    st.caption('R0.5.6 · СП 468 (таблицы 9.1–9.6) · сборка 2026-11-05')

with st.spinner('Расчёт введённых усилий'):
    calculations=evaluate_project(project,grid=48)
# Restore only diagnostics associated with unchanged source column data.
from rc_fire.integration.r064d import _signature as _r064d_signature
for _column in project['columns']:
    _key='r064d_result_'+str(_column['id'])
    _saved=st.session_state.get(_key)
    if _saved is not None and _saved.get('signature')==_r064d_signature(_column):
        calculations[_column['id']]['member_r064d']=_saved['result']
    elif _saved is not None:
        st.session_state.pop(_key,None)
if selected=='Обзор проекта':show_overview()
else:column_page(selected)