"""Streamlit presentation: R0.6.3 section equilibrium is NEVER a R90 verdict."""
from __future__ import annotations

from rc_fire.mechanics import evaluate_column_mechanics

LABELS={
 'not_evaluated':'Не рассчитано — отсутствуют исходные данные',
 'blocked':'Расчёт заблокирован областью применения',
 'evaluated_diagnostic':'Получено диагностическое равновесие сечений',
 'partially_evaluated':'Часть расчётных сечений не имеет решения',
 'equilibrium_within_strain_limits':'Равновесие и контроль деформаций выполнены',
 'strain_limits_exceeded':'Предельные деформации превышены',
 'equilibrium_not_converged':'Численное равновесие не найдено',
 'loads_missing':'Нагрузки не заданы',
}


def render_mechanics_overview(st,project,calculations):
    import pandas as pd
    with st.expander('R0.6.3 — численная механика сечений (НЕ заключение R90)',expanded=False):
        rows=[]
        for col in project['columns']:
            obj=calculations[col['id']].get('mechanics_r063') or {}
            rows.append({'Колонна':col['name'],
                'Состояние':LABELS.get(obj.get('status'),obj.get('status','недоступно')),
                'Сечений с равновесием':sum(1 for r in obj.get('sections',{}).values() if r.get('equilibrium')),
                'Всего сечений':len(col.get('sections',[])),
                'R90':'НЕ ПОДТВЕРЖДЕНО'})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.caption('Результаты сечений отделены от устойчивости элемента, spalling и определения R(t).')


def render_mechanics_results(st,column,calculation):
    import pandas as pd
    result=calculation.get('mechanics_r063') or {}
    with st.expander('R0.6.3 — температурная механика N–Mx–My',expanded=False):
        st.warning('Это **проверка равновесия одного сечения**, не подтверждение R90. '
                   'Расчёт устойчивости и воздействий от температурного защемления ещё не включён.')
        status=result.get('status','not_evaluated')
        st.write('**Результат:** '+LABELS.get(status,status))
        for issue in result.get('issues',[]):
            st.caption('— '+str(issue))
        strength=result.get('material_strengths')
        if strength:
            g1,g2,g3=st.columns(3)
            g1.metric('fcd при 20 °C, МПа',f"{strength['f_cd_MPa']:.3f}")
            g2.metric('fyd при 20 °C, МПа',f"{strength['f_yd_MPa']:.1f}")
            g3.metric('γc / γs',f"{strength['gamma_c']:.2f} / {strength['gamma_s']:.2f}")
            st.caption('СП 5.03.01-2020: таблица 4.6, формулы (6.4), (6.5), (6.28); '
                       'СП 2.02.05-2026: таблицы 9–10.')
        rows=[]
        for sid,val in result.get('sections',{}).items():
            detail=val.get('details') or {}
            rows.append({'Сечение':sid,
                 'Состояние':LABELS.get(val.get('status'),val.get('status')),
                 'Nвнутр, кН':round(val['internal']['N_kN'],3) if 'internal' in val else None,
                 'Mxвнутр, кН·м':round(val['internal']['Mx_kNm'],3) if 'internal' in val else None,
                 'Myвнутр, кН·м':round(val['internal']['My_kNm'],3) if 'internal' in val else None,
                 'Макс. εc, ‰':round(detail['max_concrete_compression']*1000,3) if detail else None,
                 'Мин. εs, ‰':round(detail['min_steel_strain']*1000,3) if detail else None,
                 'Относительная невязка':val.get('relative_residual')})
        if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        if status=='blocked' and any('800' in str(i) for i in result.get('issues',[])):
            st.info('СП 2.02.05-2026 не задаёт коэффициенты таблиц 9–10 выше 800 °C. '
                'Для исследования допускается отдельное заведомо ненормативное допущение '
                'об исключении сопротивления перегретых волокон.')
            diagnostic=st.checkbox('Исследовательский режим: прочность при T>800 °C = 0 '
                     '(не для нормативных отчётов)',value=False,
                     key=f"r063_zero_{column['id']}")
            if diagnostic:
                estimate=evaluate_column_mechanics(column,
                    calculation.get('thermal_normative'),grid=24,
                    above_800_policy='zero_strength_diagnostic')
                st.error('РЕЗУЛЬТАТ НЕ НОРМАТИВНЫЙ: прочность областей >800 °C '
                         'предположена нулевой, а не назначена нормативом.')
                st.write('**Состояние:** '+LABELS.get(estimate['status'],estimate['status']))
                st.dataframe(pd.DataFrame([{'Сечение':sid,
                    'Равновесие':v.get('equilibrium',False),
                    'Деформации':v.get('strain_limits_satisfied'),
                    'Невязка':v.get('relative_residual')} for sid,v in
                    estimate['sections'].items()]),use_container_width=True,hide_index=True)
        available=[sid for sid,v in result.get('sections',{}).items() if v.get('equilibrium')]
        if available and st.checkbox('Исследовательский контур сопротивления Mx–My при заданном N',
                value=False,key=f"r063_capacity_{column['id']}"):
            from rc_fire.mechanics import prepare_section, approximate_biaxial_capacity
            import plotly.graph_objects as go
            sid=st.selectbox('Сечение для контура',available,
                    key=f"r063_capacity_sid_{column['id']}")
            loads=next(s for s in column['sections'] if s['id']==sid)
            try:
                ready=prepare_section(column,calculation['thermal_normative'],grid=24)
                cap=approximate_biaxial_capacity(ready,loads['N_kN'],
                    loads['Mx_kNm'],loads['My_kNm'],angular_samples=36)
            except Exception as exc:
                st.error('Контур не построен: '+str(exc))
                cap={}
            if cap.get('status')=='approximate_capacity_diagnostic':
                st.metric('u≈, численная граница сечения',
                    f"{cap['utilization_diagnostic']:.4f}")
                st.error('Это приближённое численное значение. Оно НЕ является '
                    'нормативным коэффициентом использования и НЕ подтверждает R90.')
                pts=cap['envelope_Mx_My_kNm']
                fig=go.Figure()
                fig.add_scatter(x=[p[0] for p in pts]+[pts[0][0]],
                                y=[p[1] for p in pts]+[pts[0][1]],
                                mode='lines',name='Численная граница при N')
                fig.add_scatter(x=[loads['Mx_kNm']],y=[loads['My_kNm']],
                                mode='markers',marker={'size':11},name='Заданные моменты')
                fig.update_layout(xaxis_title='Mx, кН·м',yaxis_title='My, кН·м',
                                  title='Численный диагностический контур N–Mx–My')
                st.plotly_chart(fig,use_container_width=True,
                                key=f"r063_envelopeplot_{column['id']}")
            else:
                st.info('Контур сопротивления: '+str(cap.get('status','не определён')))
        if available and st.checkbox('Показать поле напряжений σc(x,y)',value=False,
                   key=f"r063_stress_{column['id']}"):
            import plotly.graph_objects as go
            sid=st.selectbox('Расчётное сечение',available,key=f"r063_sid_{column['id']}")
            illustration=evaluate_column_mechanics(column,
                    calculation.get('thermal_normative'),grid=24,include_maps=True)
            data=illustration.get('sections',{}).get(sid,{})
            if data.get('equilibrium') and data.get('details',{}).get('map'):
                z=data['details']['map']['concrete_stress_MPa']
                fig=go.Figure(go.Heatmap(z=z,x0=column['b_mm']/48.,dx=column['b_mm']/24.,
                    y0=column['h_mm']/48.,dy=column['h_mm']/24.,
                    colorbar={'title':'σc, МПа'},colorscale='Viridis'))
                fig.add_scatter(x=[b['x_mm'] for b in column['bars']],
                    y=[b['y_mm'] for b in column['bars']],mode='markers+text',
                    text=[b['id'] for b in column['bars']],textposition='top center',
                    marker={'symbol':'circle-open','size':12,'color':'black'},name='Арматура')
                fig.update_layout(title='Сжимающие напряжения бетона, МПа — '+sid,
                    xaxis_title='x, мм',yaxis_title='y, мм',yaxis={'scaleanchor':'x'},height=500)
                st.plotly_chart(fig,use_container_width=True,key=f"r063_stressmap_{column['id']}")