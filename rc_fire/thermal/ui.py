"""R0.6.2 Streamlit editor and read-only visualization for Annex K."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .normative import CONCRETE_FAMILIES, FACE_NAMES, MODEL_CHOICES, TABLE_K1

FAMILY_LABELS={
 'siliceous':'Тяжёлый бетон — силикатный заполнитель',
 'calcareous':'Тяжёлый бетон — карбонатный заполнитель',
 'expanded_clay':'Керамзитобетон (только теплотехника; прочность отдельно)',
}
FACE_LABELS={'left':'Левая','right':'Правая','bottom':'Нижняя','top':'Верхняя'}
MODE_LABELS={'table_K1':'Готовое a_red, таблица К.1',
             'formula_K1_450C':'Формула К.1, средняя температура 450 °C'}


def render_thermal_inputs(st,project,column,safe_change,update_thermal_spec):
    cid=column['id']
    spec=column.get('thermal_spec') or {}
    mat=(column.get('material_spec') or {}).get('concrete') or {}
    fallback=mat.get('aggregate_family')
    with st.expander('R0.6.2 — нагрев бетона и арматуры (СП 2.02.05-2026, приложение К)',expanded=False):
        st.caption('Нормативный аналитический расчёт температур по К.1–К.12; '
                   'одна, две, три или четыре нагреваемые стороны. '
                   'Для подтверждения R требуется отдельная проверка несущей способности.')
        with st.form(f'{cid}_thermal_annexK_rev{project["revision"]}'):
            families=[None]+list(CONCRETE_FAMILIES)
            cur=spec.get('concrete_family',fallback)
            family=st.selectbox('Бетон для теплотехники (табл. К.1)',families,
                index=families.index(cur) if cur in families else 0,
                format_func=lambda x:'— укажите бетон —' if x is None else FAMILY_LABELS[x],
                help='Если указан материал R0.6.1, вид заполнителя должен совпадать.')
            rho=st.text_input('Сухая плотность, кг/м³ (таблица К.2: 800–2400)',
                value='' if spec.get('dry_density_kg_m3') is None else f'{float(spec["dry_density_kg_m3"]):g}',
                help='Без сухой плотности φ1 и φ2 не определяются. Значение не придумывается из класса C30/37.')
            choice=spec.get('a_red_mode','table_K1')
            mode=st.selectbox('Температуропроводность a_red',MODEL_CHOICES,
                index=MODEL_CHOICES.index(choice) if choice in MODEL_CHOICES else 0,
                format_func=lambda x:MODE_LABELS[x])
            wc=st.text_input('Весовая влажность Wc, % (при пустом поле — табл. К.1)',
                value='' if spec.get('moisture_mass_pct') is None else f'{float(spec["moisture_mass_pct"]):g}',
                help='При выборе готового табличного a_red изменение Wc невозможно: для иной влажности '
                     'используйте формулу К.1.')
            current_faces=spec.get('exposed_faces',list(FACE_NAMES))
            exposed=st.multiselect('Огневое воздействие — нагреваемые грани',options=list(FACE_NAMES),
                default=[s for s in current_faces if s in FACE_NAMES],
                format_func=lambda x:FACE_LABELS[x])
            if family in TABLE_K1:
                st.caption('Таблица К.1: a_red = '+f'{TABLE_K1[family]["a_red_m2_h"]:.6g} м²/ч; '
                           'Wc = '+f'{TABLE_K1[family]["Wc_pct"]:.1f} %')
            if st.form_submit_button('Сохранить теплотехнические параметры'):
                def asnum(v):return None if not v.strip() else float(v.replace(',','.'))
                try:
                    values={'concrete_family':family,'a_red_mode':mode,
                            'dry_density_kg_m3':asnum(rho),
                            'moisture_mass_pct':asnum(wc),
                            'exposed_faces':exposed}
                except ValueError:
                    st.error('Влажность и плотность должны быть числами')
                else:
                    safe_change(update_thermal_spec,project,cid,values)


def _temperature_figure(thermal,column):
    field=thermal['field'];z=field['temperature_C'];x=field['x_mm'];y=field['y_mm']
    fig=go.Figure()
    fig.add_trace(go.Heatmap(x=x,y=y,z=z,colorscale='Inferno',
        colorbar={'title':'°C'},hovertemplate='x=%{x:.0f} мм, y=%{y:.0f} мм, θ=%{z:.1f} °C<extra></extra>'))
    threshold=thermal.get('critical_temperature_C')
    if threshold is not None and min(min(row) for row in z) < threshold < max(max(row) for row in z):
        fig.add_trace(go.Contour(x=x,y=y,z=z,contours={'start':threshold,'end':threshold,'size':1,
            'coloring':'none','showlabels':True},line={'color':'white','width':2},showscale=False,
            hoverinfo='skip',name=f'{threshold:g} °C'))
    bars=thermal.get('reinforcement',[])
    if bars:
        fig.add_trace(go.Scatter(x=[b['x_mm'] for b in bars],y=[b['y_mm'] for b in bars],
            mode='markers+text',text=[b['id'] for b in bars],textposition='top center',
            marker={'symbol':'circle','size':[max(7,b['diameter_mm']*.9) for b in bars],
                    'color':'#3fd8ff','line':{'color':'black','width':1}},
            customdata=[[b['theta_C'],b['diameter_mm']] for b in bars],
            hovertemplate='Стержень %{text}: θ=%{customdata[0]:.1f} °C, '
                          'Ø%{customdata[1]:g} мм<extra></extra>',name='Арматура'))
    fig.update_layout(xaxis={'title':'x, мм','range':[0,float(column['b_mm'])]},
                      yaxis={'title':'y, мм','range':[0,float(column['h_mm'])],
                             'scaleanchor':'x','scaleratio':1},
                      margin={'l':20,'r':10,'t':10,'b':20},height=480,
                      legend={'orientation':'h'})
    return fig


def render_thermal_results(st,column,calc):
    th=calc.get('thermal_normative') or {}
    if not th:return
    st.subheader('R0.6.2 — температурное поле и температура арматуры')
    status=th.get('status','not_evaluated')
    if status=='not_evaluated':
        st.info('Не хватает данных: '+', '.join(th.get('missing',[]))+
                '. Введите их в разделе теплотехнических параметров.')
        return
    if status=='invalid':
        st.error('Теплотехнический расчёт недопустим: '+th.get('reason','ошибка входных данных'))
        return
    coeff=th['coefficients']
    st.caption('СП 2.02.05-2026, приложение К, '+th['formula']+
               '; а_red='+f'{coeff["a_red_m2_h"]:.6f}'+' м²/ч, φ1='+
               f'{coeff["phi_1"]:.3f}'+', φ2='+f'{coeff["phi_2"]:.3f}'+
               '. Время: '+str(th['fire_minutes'])+' мин.')
    if th.get('issues'):
        st.warning('Ограничения: '+'; '.join(th['issues']))
    st.plotly_chart(_temperature_figure(th,column),use_container_width=True,
                    key=f'{column["id"]}_thermal_K_field')
    bars=th.get('reinforcement',[])
    if bars:
        st.dataframe(pd.DataFrame([{'Стержень':b['id'],'x, мм':b['x_mm'],
                                   'y, мм':b['y_mm'],'Ø, мм':b['diameter_mm'],
                                   'Температура, °C':round(b['theta_C'],2)}
                                   for b in bars]),hide_index=True,use_container_width=True)
    crit=th.get('critical_section',{})
    if crit.get('status')=='evaluated':
        st.write('Критическая изотерма '+str(th['critical_temperature_C'])+' °C. '
                 'Площадь остаточного сечения (К.27): '
                 +f'{crit["remaining_area_m2"]:.5f}'+' м².')
    else:
        st.caption('Формула К.27 для остаточной площади не применяется: '+
                   crit.get('reason','требуется отдельное определение сечения'))
    st.caption('Температурный расчёт ещё НЕ означает подтверждение R90. '
               'Механика и устойчивость проходят отдельную нормативную проверку.')


def render_thermal_overview(st,project,calculations):
    rows=[]
    for c in project['columns']:
        t=calculations[c['id']].get('thermal_normative') or {}
        bars=t.get('reinforcement') or []
        rows.append({'Колонна':c['name'],'К':t.get('formula','—'),
                     'Теплотехника':t.get('status','—'),
                     'max θ арматуры, °C':None if not bars else round(max(b['theta_C'] for b in bars),1),
                     'Критическая изотерма, °C':t.get('critical_temperature_C')})
    st.markdown('**R0.6.2 — нагрев бетонного сечения и арматуры**')
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)