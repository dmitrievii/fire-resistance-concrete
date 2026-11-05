"""Streamlit R0.5.6 panels: user-input spalling, member and biaxial diagnostics."""
from __future__ import annotations
import pandas as pd
from multicolumn_r05.r056_engine import SPALLING_FIELDS, SPALLING_UNITS
from multicolumn_r05.project_model import update_spalling


def render_spalling_inputs(st, project, column, safe_change):
    cid=column['id'];stored=column.get('spalling') or {}
    with st.expander('Хрупкое разрушение бетона — коэффициенты критерия F',expanded=False):
        st.caption('Формула (3.4.1) исходного отчёта К18. Без всех коэффициентов F не рассчитывается. '
                   'Величины вводятся в единицах, указанных в отчёте; это не автоматическая '
                   'оценка состава бетона по одному классу прочности.')
        with st.form(key=f'r056_spall_{cid}_rev{project["revision"]}'):
            values={};cols=st.columns(3)
            for i,key in enumerate(SPALLING_FIELDS):
                with cols[i%3]:
                    v=stored.get(key)
                    values[key]=st.text_input(key, value='' if v is None else f'{v:g}',
                        help=SPALLING_UNITS.get(key,''))
            submitted=st.form_submit_button('Сохранить параметры F')
            if submitted:
                safe_change(update_spalling,project,cid,values)


def _ru_spall(calc):
    s=calc.get('spalling',{})
    stat=s.get('status','not_evaluated')
    if stat=='not_evaluated':return 'Нет исходных коэффициентов'
    if stat=='protection_required':return 'F > 4 — требуется защита'
    if stat=='index_at_or_below_threshold':return 'F ≤ 4 — критерий выполнен'
    return 'Ошибка исходных данных'


def render_r056_results(st,calc):
    st.subheader('R0.5.6 — дополнительные расчётные проверки')
    st.caption('Отдельно показаны: общий конверт η, численное совместное равновесие N–Mx–My '
               'и критерий F из оригинального отчёта. Результаты диагностические; '
               'национальная нормативная проверка R90 не утверждается.')
    member=calc.get('member',{})
    if member.get('status')=='evaluated':
        st.markdown('**Устойчивость по всей колонне — общий Nmax и Ncr,min**')
        st.dataframe(pd.DataFrame([{
            'Ось':axis.upper(), 'Nmax, кН':member['Nmax_kN'],
            'Ncr,min, кН':v['Ncr_min_kN'],'η колонны':v['eta_member']
        } for axis,v in member['axes'].items()]),hide_index=True,use_container_width=True)
    elif member.get('status')=='instability_or_invalid':
        st.error('Общий расчётный конверт: Nmax ≥ Ncr,min или некорректная жёсткость.')
    else:
        st.info('Общий конверт устойчивости будет доступен после ввода усилий.')
    biax=calc.get('biaxial',{})
    if biax.get('sections'):
        st.markdown('**Совместное численное равновесие N–Mx–My**')
        st.dataframe(pd.DataFrame([{
            'Сечение':sid,'Статус':rec['status'],
            'Δ равновесия':rec.get('residual_norm'),
            'εc,max':rec.get('eps_c_max'),
            'Mx, кН·м':rec['Mx_demand_kNm'],'My, кН·м':rec['My_demand_kNm']
        } for sid,rec in biax['sections'].items()]),hide_index=True,use_container_width=True)
    else:
        st.info('Совместная проверка недоступна, пока не рассчитан общий конверт.')
    sp=calc.get('spalling',{})
    st.markdown('**Хрупкое разрушение бетона — критерий F**')
    st.write(_ru_spall(calc))
    if sp.get('F') is not None:
        st.metric('F (порог 4,0)',f'{sp["F"]:.4f}')
    elif sp.get('status')=='not_evaluated':
        st.caption('Отсутствуют: '+', '.join(sp.get('missing',[])))
    elif sp.get('status')=='invalid':
        st.error(sp.get('error','Некорректный коэффициент F'))
    st.warning('R90 не подтверждено нормативно: наличие численного равновесия, '
               'достаточной жёсткости и F ≤ 4 само по себе не завершает '
               'нормативную проверку устойчивости, двухосного действия и теплового разрушения.')


def render_r056_overview(st,project,calculations):
    st.markdown('**Дополнительные проверки R0.5.6**')
    rows=[]
    for c in project['columns']:
        x=calculations[c['id']]
        b=x.get('biaxial',{})
        states=[v['status'] for v in b.get('sections',{}).values()]
        rows.append({'Колонна':c['name'],
                     'Общий конверт η':x.get('member',{}).get('status','—'),
                     'Совместное N–Mx–My':(', '.join(sorted(set(states))) if states else 'Не рассчитано'),
                     'Критерий F':_ru_spall(x),
                     'Итоговое R90':'Не подтверждено'})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)